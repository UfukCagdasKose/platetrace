# AGIS Dashboard

Vue 3 + Vite panel: dört analitik ucun (`/konvoylar`, `/klonlar`,
`/anomaliler`, `/aranan/eslesmeler`) her biri icin bir sekme, canli veri
cekip gorsellestiriyor. Router, state kutuphanesi, UI framework, chart
kutuphanesi yok -- bilerek kucuk tutuldu; sekme gecisi `App.vue`'de duz
bir `shallowRef`, grafikler el yazimi CSS/SVG (dataviz skill'inin form/
renk/etiket kurallarina gore: buyukluk kiyasi icin tek renkli yatay
cubuk -- konvoy agirligi, klonlama hizi/esik -- kimlik ayrimi icin
kategorik yigin bar -- anomali turu, eslesme kesinligi -- hicbir sayi
uydurulmuyor).

`src/api.js`'deki `useKaynak()` her sekmenin tekrarladigi fetch/durum
iskeletini topluyor; `src/components/` altinda `Plaka` (gercek Turk
plakasi rozeti), `StatKutu` (ozet halkasi), `DurumMesaji` (yukleniyor/
hata/bos durumlari) paylasilan parcalar.

## Calistirma

**En basit yol:** repo kokunden `docker compose up --build` -- `db`,
`api` ve `dashboard` servislerinin ucunu de ayaga kaldirir,
http://localhost:5173.

**Ayri ayri:**

```bash
# API (ayrı bir terminalde)
python3 -m venv .venv-api && source .venv-api/bin/activate
pip install -r ../requirements-api.txt
cd .. && uvicorn app.main:app --reload

# Dashboard
cd dashboard
npm install
npm run dev          # http://localhost:5173
```

API'nin adresi `VITE_API_BASE` ile ayarlanir (varsayilan
`http://localhost:8000`; docker-compose'da `environment:` ile aciqca
`http://localhost:8000` set ediliyor -- fetch tarayicida calistigi icin
Docker network adi `api:8000` degil, host'tan gorunen yayinlanmis port
dogru). API sadece `http://localhost:5173` ve `http://127.0.0.1:5173`
origin'lerine CORS izni veriyor (bkz. `app/main.py`); baska bir portta
calistirirsan orayi da eklemen gerekir.

## Örnek veri üretmek

Tek bir planted senaryoyla sayfa oldukca bos gorunuyor. Zengin bir demo
veri seti icin `synth_scenario.py`'yi birden fazla tohumla ayni
veritabanina yukle:

```bash
source ../.venv/bin/activate   # requirements-ml.txt (torch, networkx, sqlalchemy)

# Dockerized Postgres'e yuklemek icin:
export DATABASE_URL="postgresql+psycopg://agis:agis@localhost:5432/agis"
# ya da bagimsiz bir SQLite dosyasi icin:
# export DATABASE_URL="sqlite:////tmp/dashboard_demo.db"

cd ..
python3 -c "from app.db import Base, engine; import app.models; Base.metadata.create_all(bind=engine)"
for seed in 11 12 13 14 15; do
    python3 synth_scenario.py --out /tmp/demo_seed$seed --seed $seed --load-db
done
```

Her `--load-db` cagrisi kendi sehir topolojisini (Nokta satirlari) ve
kendi planted olaylarini ekliyor -- ayni DATABASE_URL'e birden fazla kez
yazmak, bagimsiz senaryolari biriktiriyor.

**Bilinen sinir:** `Base.metadata.create_all()` var olan bir tabloyu
DEGISTIRMEZ, sadece eksik tabloyu olusturur. Şema `app/models.py`'de
degisirse (ornegin bir kisit kaldirilirsa) ve DB'de o tablo zaten
varsa, degisiklik oraya hic ulasmaz -- projede Alembic gibi bir
migration araci yok. Boyle bir uyusmazlik yasarsan ya volume'u sifirla
(`docker compose down -v`) ya da elle `ALTER TABLE` calistir.

## Durum

Dort görünüm de tamam, `docker-compose.yml`'e bağlı. Henüz yok:
grafiklerde filtre/zaman araligi, sayfalama (buyuk veri setlerinde
tum sonuc tek seferde cekiliyor).
