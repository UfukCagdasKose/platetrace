"""AGIS API - Arac Gecis Istihbarat Sistemi.

Gecis kaydi yazma/okuma + analitik uclari (konvoy, klonlama, rota/zaman
anomalisi, aranan arac fuzzy eslesme). Analitik modulleri (convoy.py,
cloning.py, anomalies.py, watchlist.py) synth_scenario.py'nin urettigi
CSV yerine dogrudan veritabanindaki GecisKaydi/Nokta/ArananArac satirlarini
okuyor -- ayni fonksiyonlar, farkli veri kaynagi.
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from anomalies import MIN_DISTINCT_DAYS, ODD_HOUR_THRESHOLD_HOURS, detect_anomalies
from app.db import Base, engine, get_db
from app.models import ArananArac, GecisKaydi, Nokta
from cloning import MAX_PLAUSIBLE_SPEED_KMH, detect_clones
from convoy import detect_convoys
from watchlist import find_matches

# convoy.py'nin CLI'siyla ayni: eval_convoy.py'de olculup kalibre edildi.
CONVOY_MIN_WEIGHT = 0.025

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AGIS", version="0.1.0", lifespan=lifespan)


class GecisIn(BaseModel):
    plaka: str
    nokta_id: int
    zaman: datetime
    guven: float = 0.0
    arac_tipi: str = "unknown"


class GecisOut(GecisIn):
    id: int

    class Config:
        from_attributes = True


@app.get("/health")
def health(db: Session = Depends(get_db)):
    gecis_sayisi = db.scalar(select(GecisKaydi.id).limit(1))
    return {"status": "ok", "db": "up", "veri_var": gecis_sayisi is not None}


@app.post("/gecisler", response_model=GecisOut)
def gecis_ekle(gecis: GecisIn, db: Session = Depends(get_db)):
    kayit = GecisKaydi(**gecis.model_dump())
    db.add(kayit)
    db.commit()
    return kayit


@app.get("/gecisler", response_model=list[GecisOut])
def gecisleri_listele(
    plaka: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = select(GecisKaydi).order_by(GecisKaydi.zaman.desc()).limit(limit)
    if plaka:
        query = query.where(GecisKaydi.plaka == plaka.upper())
    return list(db.scalars(query))


@app.get("/noktalar")
def noktalari_listele(db: Session = Depends(get_db)):
    return list(db.scalars(select(Nokta)))


@app.get("/aranan")
def aranan_listele(db: Session = Depends(get_db)):
    return list(db.scalars(select(ArananArac)))


def _gecis_rows(db, limit):
    """convoy/cloning/anomalies'in bekledigi plaka/nokta_id/zaman alanlarina
    sahip dict listesi -- ORM nesnesi degil, cunku bu modulller CSV'den
    okunan plain dict'lerle test edildi (bkz. convoy.load_gecis_csv).

    `if limit:` DEGIL `is not None`: limit=0 "hic satir donme" demek,
    ama 0 Python'da falsy oldugu icin `if limit:` onu sessizce yok sayip
    TUM satirlari donerdi."""
    query = select(GecisKaydi).order_by(GecisKaydi.zaman.desc())
    if limit is not None:
        query = query.limit(limit)
    return [{"plaka": r.plaka, "nokta_id": r.nokta_id, "zaman": r.zaman}
            for r in db.scalars(query)]


@app.get("/konvoylar")
def konvoylar(
    window_seconds: int = 600,
    min_distinct_points: int = 2,
    min_weight: float = CONVOY_MIN_WEIGHT,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    """Konvoy adaylari: bkz. convoy.py. min_weight varsayilani
    eval_convoy.py'de senaryo verisine karsi kalibre edildi (0.025);
    farkli trafik hacminde yeniden olculmesi gerekebilir."""
    rows = _gecis_rows(db, limit)
    components, g = detect_convoys(rows, window_seconds, min_distinct_points, min_weight)
    return [
        {
            "plakalar": sorted(comp),
            "kenarlar": [
                {"a": a, "b": b, "weight": round(data["weight"], 4), "noktalar": data["points"]}
                for a, b, data in g.subgraph(comp).edges(data=True)
            ],
        }
        for comp in components if len(comp) >= 2
    ]


@app.get("/klonlar")
def klonlar(
    max_speed: float = MAX_PLAUSIBLE_SPEED_KMH,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    """Fiziksel olarak imkansiz hiz gerektiren plaka-cifti okumalari: bkz. cloning.py.

    GecisKaydi.nokta_id uzerinde bir foreign key kisiti yok (bkz.
    app/models.py); yani /gecisler'e uydurma bir nokta_id'yle kayit
    eklemek mumkun. cloning.detect_clones her okumanin noktasini
    points[nokta_id] ile arar -- nokta tabloda yoksa KeyError'la 500'e
    duser. Boyle bir satiri sessizce atlamak (analiz disi birakmak),
    tum istegi patlatmaktan daha dogru bir davranis."""
    rows = _gecis_rows(db, limit)
    points = {n.id: (n.enlem, n.boylam) for n in db.scalars(select(Nokta))}
    rows = [r for r in rows if r["nokta_id"] in points]
    return detect_clones(rows, points, max_speed)


@app.get("/anomaliler")
def anomaliler(
    min_distinct_days: int = MIN_DISTINCT_DAYS,
    odd_hour_threshold: float = ODD_HOUR_THRESHOLD_HOURS,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    """Rota/zaman anomalileri: bkz. anomalies.py. min_distinct_days
    varsayilani eval_anomalies.py'de kalibre edildi (5)."""
    rows = _gecis_rows(db, limit)
    return detect_anomalies(rows, min_distinct_days, odd_hour_threshold)


@app.get("/aranan/eslesmeler")
def aranan_eslesmeler(
    max_distance: int = 1,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    """Son `limit` gecis kaydini aranan arac listesine karsi bulanik
    (fuzzy) eslestirir: bkz. watchlist.py."""
    watchlist = list(db.scalars(select(ArananArac)))
    if not watchlist:
        return []

    query = select(GecisKaydi).order_by(GecisKaydi.zaman.desc()).limit(limit)
    eslesmeler = []
    for gecis in db.scalars(query):
        for entry, dist in find_matches(gecis.plaka, watchlist, max_distance=max_distance):
            eslesmeler.append({
                "gecis_id": gecis.id,
                "okunan_plaka": gecis.plaka,
                "aranan_plaka": entry.plaka,
                "sebep": entry.sebep,
                "mesafe": dist,
                "nokta_id": gecis.nokta_id,
                "zaman": gecis.zaman,
            })
    return eslesmeler
