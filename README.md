# AGIS — Araç Geçiş İstihbarat Sistemi

Kamera görüntüsünden araç ve plaka tespiti yaparak yapılandırılmış geçiş
kayıtları üreten; bu kayıtlar üzerinde birlikte hareket eden araç ağlarını,
plaka klonlama şüphesini ve rota anomalilerini çıkaran sistem.

## Durum

- [x] Docker iskeleti (API + PostgreSQL)
- [x] Veritabanı şeması (geçiş kaydı, nokta, aranan araç)
- [x] Sentetik plaka üreteci
- [ ] Plaka tespiti (YOLO fine-tune)
- [ ] Plaka OCR
- [ ] Takip + karakter oylaması
- [ ] Analitik katman (konvoy, klonlama, anomali)
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

## Proje yapısı

```
agis/
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
└── train_detector.py        # YOLO fine-tune
```

## Veri ve gizlilik

Gerçek plaka ve kamera verisi kullanılmaz. Plaka, KVKK kapsamında kişisel
veri niteliğindedir. Tespit modeli açık veri setleriyle, OCR modeli bu
projede üretilen sentetik veriyle eğitilir.
