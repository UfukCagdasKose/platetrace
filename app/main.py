"""AGIS API - Arac Gecis Istihbarat Sistemi.

Su an sadece iskelet: saglik kontrolu, gecis kaydi yazma/okuma.
Analitik uclari (konvoy, klonlama, watchlist) 3. haftada eklenecek.
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import ArananArac, GecisKaydi, Nokta

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
