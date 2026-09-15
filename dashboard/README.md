# AGIS Dashboard

Vue 3 + Vite ile yazılan minimal bir baslangic: tek sayfa, `/konvoylar`
ucundan gercek zamanli veri cekip gorsellestiriyor (bkz. `src/App.vue`).
Router, state kutuphanesi, UI framework, chart kutuphanesi yok -- bilerek
kucuk tutuldu; grafikler el yazimi CSS/SVG (dataviz skill'inin form/renk/
etiket kurallarina gore: buyukluk kiyasi icin tek renkli yatay cubuk,
iliski icin dugum-kenar grafi, hicbir sayi uydurulmuyor).

## Ornek veri uretmek

Sayfa tek bir planted konvoyla oldukca bos gorunuyor. Zengin bir demo
veri seti icin `synth_scenario.py`'yi birden fazla tohumla ayni
veritabanina yukle (once tablolari olustur):

```bash
source ../.venv/bin/activate   # requirements-ml.txt (torch, networkx, sqlalchemy)
export DATABASE_URL="sqlite:////tmp/dashboard_demo.db"
cd ..
python3 -c "from app.db import Base, engine; import app.models; Base.metadata.create_all(bind=engine)"
for seed in 11 12 13 14 15; do
    python3 synth_scenario.py --out /tmp/demo_seed$seed --seed $seed --load-db
done
```

Her `--load-db` cagrisi kendi sehir topolojisini (Nokta satirlari) ve
kendi planted konvoyunu ekliyor -- ayni DATABASE_URL'e birden fazla kez
yazmak, bagimsiz senaryolari biriktiriyor.

## Calistirma

API ayrica ayakta olmali (`docker compose up` ya da yerelde `uvicorn`).
API'nin adresi `.env` dosyasinda `VITE_API_BASE` ile ayarlanabilir,
varsayilan `http://localhost:8000`.

```bash
npm install
npm run dev          # http://localhost:5173
```

API, sadece `http://localhost:5173` ve `http://127.0.0.1:5173`
origin'lerine CORS izni veriyor (bkz. `app/main.py`); baska bir portta
calistirirsan orayi da eklemen gerekir.

## Durum

Şu an sadece konvoy listesi var. `/klonlar`, `/anomaliler`,
`/aranan/eslesmeler` icin sayfa/gorunum henuz yok -- CLAUDE.md'deki
roadmap'e bakilabilir.
