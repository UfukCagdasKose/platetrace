# AGIS — Araç Geçiş İstihbarat Sistemi

Kamera görüntüsünden araç ve plaka tespiti yaparak yapılandırılmış geçiş
kayıtları üreten; bu kayıtlar üzerinde birlikte hareket eden araç ağlarını,
plaka klonlama şüphesini ve rota anomalilerini çıkaran sistem.

## Durum

- [x] Docker iskeleti (API + PostgreSQL)
- [x] Veritabanı şeması (geçiş kaydı, nokta, aranan araç)
- [x] Sentetik plaka üreteci
- [x] Plaka tespiti (YOLO26 fine-tune, mAP50 0.993 / mAP50-95 0.882 — `train_detector.py`)
- [x] Plaka OCR (CRNN+CTC, sentetik veride 100% val exact-match — ancak bu,
      egitimle ayni bozulma dagilimindan gelen bir val split; gercekci
      kosullarda (severity 0.0-0.3) %90-96 exact-match, agir bozulmada
      (severity 1.0) %14'e dusuyor — `train_ocr.py`, `eval_ocr.py`)
- [x] Karakter oylaması (track içi çoğunluk oylaması; sentetik track
      simülasyonunda tek kare OCR'a göre +12 ila +44 puan doğruluk kazancı
      — `voting.py`, `eval_voting.py`)
- [x] Tespit+OCR pipeline'ı (`pipeline.py`) — geçiş kaydı üretip veritabanına
      yazıyor; henüz takip yok, her tespit tek kare olarak okunuyor (oylama
      uygulanmıyor)
- [ ] Takip (ByteTrack; gerçek/hareketli video gerektiriyor, henüz yok)
- [x] Sentetik senaryo üreteci (planted olaylarla: konvoy, rutin birlikte
      seyahat — yanlış pozitif tuzağı, klonlanmış plaka, rota/zaman
      anomalisi; her okuma gerçek OCR checkpoint'inden geçiriliyor —
      `synth_scenario.py`)
- [x] Bulanık (fuzzy) aranan araç eşleştirme (Levenshtein ≤1, OCR
      karışıklıklarına toleranslı: 0↔O, 1↔İ, 8↔B, 5↔S; tam metin
      eşleşmesine göre recall %50→%90 (severity 0.6), %33→%67
      (severity 0.8), sıfır kesinlik bedeliyle — `watchlist.py`,
      `eval_watchlist.py`)
- [x] Konvoy tespiti (trafik hacmine göre normalize edilmiş kenar ağırlığı
      + en az 2 farklı ortak nokta şartı; rutin birlikte seyahat eden
      çifti 7 rastgele tohumda 0 yanlış pozitifle eliyor — `convoy.py`,
      `eval_convoy.py`)
- [x] Plaka klonlama tespiti (iki nokta arasında fiziksel olarak imkânsız
      hız, > 150 km/h; planted klonu 7 tohumda 0 yanlış pozitifle
      yakalıyor — `cloning.py`, `eval_cloning.py`)
- [x] Rota/zaman anomali tespiti (aracın kendi geçmişine göre alışılmadık
      nokta/saat; 8 tohumda 15/16 planted anomaliyi 0 yanlış pozitifle
      yakalıyor — `anomalies.py`, `eval_anomalies.py`)
- [ ] Vue dashboard

## Kurulum

### 1. Servisleri ayağa kaldır

```bash
docker compose up --build
```

Kontrol: http://localhost:8000/health ve http://localhost:8000/docs

### 2. Model tarafı için yerel ortam

Docker imajı sadece API'yi taşıyor; model eğitimi yerelde yapılır.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-ml.txt
```

## Kullanım

### Sentetik plaka verisi üret

```bash
# Önce görsel kontrol: 50 tane bozulmamış plaka
python3 tools/synth_plates.py --count 50 --out data/preview --clean --width 520 --height 110

# Eğitim seti
python3 tools/synth_plates.py --count 20000 --out data/synth_plates
```

`data/synth_plates/labels.txt` içinde `dosya_yolu<TAB>plaka_metni` formatında
etiketler bulunur.

### Plaka tespit modelini eğit

Roboflow Universe üzerinden YOLOv8 formatında bir plaka veri seti indir
(ör. `plakatanima-vnt3k/turkish-number-plates`), `data/plates/` altına
çıkar, sonra:

```bash
python3 train_detector.py --data data/plates/data.yaml --epochs 30
```

### Analitik senaryosu üret ve değerlendir

Planted olaylı (konvoy, rutin birlikte seyahat, klonlanmış plaka, rota/zaman
anomalisi) sentetik bir senaryo, gerçek OCR checkpoint'inden geçirilmiş
okumalarla:

```bash
python3 synth_scenario.py --out data/scenario

python3 eval_watchlist.py --scenario data/scenario
python3 eval_convoy.py --scenario data/scenario
python3 eval_cloning.py --scenario data/scenario
python3 eval_anomalies.py --scenario data/scenario
```

Her `eval_*.py`, kendi modülünü senaryonun `ground_truth.json` dosyasındaki
planted olaylara karşı ölçüp precision/recall rakamı basar.

## Proje yapısı

```
platetrace/
├── docker-compose.yml       # API + PostgreSQL
├── Dockerfile
├── requirements-api.txt     # Docker içine giren bağımlılıklar
├── requirements-ml.txt      # Yerel model ortamı
├── app/
│   ├── main.py              # FastAPI uçları
│   ├── db.py                # Veritabanı bağlantısı
│   └── models.py            # Şema: GecisKaydi, Nokta, ArananArac
├── tools/
│   └── synth_plates.py      # Sentetik plaka üreteci
├── train_detector.py        # YOLO fine-tune (plaka tespiti)
├── train_ocr.py             # CRNN+CTC eğitimi (plaka OCR)
├── eval_ocr.py              # OCR degradasyon eğrisi
├── voting.py                # Track içi karakter oylaması
├── eval_voting.py           # Oylama vs. tek kare OCR karşılaştırması
├── pipeline.py              # Tespit+OCR -> GecisKaydi
├── synth_scenario.py        # Planted olaylı analitik senaryo üreteci
├── watchlist.py             # Bulanık aranan araç eşleştirme
├── convoy.py                # Konvoy tespiti
├── cloning.py               # Plaka klonlama tespiti
├── anomalies.py             # Rota/zaman anomali tespiti
└── eval_watchlist.py, eval_convoy.py, eval_cloning.py, eval_anomalies.py
                              # Her analitik modül için ground-truth'a karşı ölçüm
```

## Veri ve gizlilik

Gerçek plaka ve kamera verisi kullanılmaz. Plaka, KVKK kapsamında kişisel
veri niteliğindedir. Tespit modeli açık veri setleriyle, OCR modeli bu
projede üretilen sentetik veriyle eğitilir.
