"""Analitik katmani icin planted-event'li sentetik senaryo ureteci.

CLAUDE.md, "Design decisions already made":
    "Analytics evaluated on a generated scenario set with planted events.
    A synthetic city topology with known convoys, a known cloned plate and
    known anomalies, so precision/recall are real numbers rather than
    impressions. OCR error should be injected using the error distribution
    measured from the actual OCR model, closing the loop between the layers."

Bu script tam olarak bunu yapar:
  1. Sentetik bir sehir topolojisi kurar (Nokta'lar, enlem/boylam).
  2. Arac nufusu simule eder: duzenli gidip-gelen (commuter) araclar +
     rastgele tek seferlik arka plan trafigi (konvoy tespitinin trafik
     hacmine gore normalize edilmesi icin gereken hacmi saglar).
  3. Bilinen olaylari eker:
       - bir konvoy (birden fazla noktada birlikte gorulen araclar)
       - "rutin birlikte seyahat" (ayni saatte ayni rotayi paylasan iki
         komsu-tipi commuter) -> KONVOY DEGIL, yanlis pozitif tuzagi
       - bir klonlanmis plaka (iki nokta arasinda fiziksel olarak
         imkansiz hizda "seyahat")
       - rota/zaman anomalileri (bir commuter'in alismadigi saatte/noktada
         gorulmesi)
       - watchlist (ArananArac) eslesmeleri, bir kismi trafikte gorunur
  4. Her okumayi gercek OCR checkpoint'inden (train_ocr.CRNN, eval_ocr'daki
     harsh_degrade) gecirip karakter hatasi enjekte eder. gecis_kaydi.plaka
     gurultulu okuma, clean_plaka ground-truth degerdir -> iki katman
     arasindaki dongu boylece gercek OCR hata dagilimiyla kapanir.

Cikti (--out altinda):
    nokta.csv        (id, ad, enlem, boylam)
    gecis_kaydi.csv  (plaka, nokta_id, zaman, guven, arac_tipi,
                       clean_plaka, event_tag, event_id — son 3'u sadece
                       degerlendirme icin, DB'ye yazilmaz)
    aranan_arac.csv  (plaka, sebep)
    ground_truth.json (planted olaylarin plate/nokta/zaman detaylari)

Kullanim:
    python3 synth_scenario.py --out data/scenario
    python3 synth_scenario.py --out data/scenario --load-db
"""

import argparse
import csv
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import torch

sys.path.insert(0, "tools")
from synth_plates import LETTER_DIGIT_RULES, PLATE_LETTERS, random_plate_text, render_clean_plate

from eval_ocr import harsh_degrade, load_model
from train_ocr import greedy_decode_with_confidence

POINT_NAMES = [
    "Cevre Yolu Girisi", "Sehir Merkezi Kavsagi", "Otoyol Gise",
    "Sanayi Bolgesi", "Havalimani Yolu", "Universite Kampusu",
    "Liman Girisi", "Dogu Girisi", "Bati Cikisi", "Merkez Otogar",
    "Kuzey Koprusu", "Guney Kavsagi",
]

WATCHLIST_REASONS = [
    "Kayip arac ihbari", "Guvenlik izleme listesi",
    "Finansal sorusturma", "Aranan sahis araci",
]

MAX_PLAUSIBLE_SPEED_KMH = 150.0  # bunun uzerindeki hiz fiziksel olarak imkansiz kabul edilir


def parse_plate(text):
    """pipeline.py'deki ayni format kontrolu (kod tekrari kasitli — pipeline.py
    ultralytics/YOLO'yu da import eder, sadece bu fonksiyon icin o agir
    zinciri tetiklemeye degmez)."""
    if len(text) < 5 or not text[:2].isdigit():
        return None
    province = text[:2]
    if not (1 <= int(province) <= 81):
        return None
    rest = text[2:]
    n_letters = 0
    while n_letters < len(rest) and rest[n_letters] in PLATE_LETTERS:
        n_letters += 1
    letters, digits = rest[:n_letters], rest[n_letters:]
    if n_letters not in LETTER_DIGIT_RULES:
        return None
    lo, hi = LETTER_DIGIT_RULES[n_letters]
    if not (digits.isdigit() and lo <= len(digits) <= hi):
        return None
    return province, letters, digits


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def generate_points(n):
    # Sentetik sehir: ~25km x 25km bir kutu icinde rastgele noktalar.
    # Gercek kamera konumu degil, sadece mesafe/hiz akil yurutmesi icin bir topoloji.
    base_lat, base_lon = 39.92, 32.85
    names = (POINT_NAMES * (n // len(POINT_NAMES) + 1))[:n]
    random.shuffle(names)
    points = []
    for i in range(n):
        lat = base_lat + random.uniform(-0.11, 0.11)
        lon = base_lon + random.uniform(-0.14, 0.14)
        points.append({"id": i + 1, "ad": f"{names[i]} ({i + 1})", "enlem": lat, "boylam": lon})
    return points


def new_plate(used):
    while True:
        province, letters, digits = random_plate_text()
        text = f"{province}{letters}{digits}"
        if text not in used:
            used.add(text)
            return province, letters, digits, text


def travel_seconds(p1, p2, speed_kmh):
    dist = haversine_km(p1["enlem"], p1["boylam"], p2["enlem"], p2["boylam"])
    return dist / speed_kmh * 3600.0, dist


class Event:
    """Tek bir plaka okuma olayi: OCR gurultusu eklenmeden once."""

    def __init__(self, province, letters, digits, nokta_id, zaman, tag, event_id):
        self.province, self.letters, self.digits = province, letters, digits
        self.clean_plaka = f"{province}{letters}{digits}"
        self.nokta_id = nokta_id
        self.zaman = zaman
        self.tag = tag
        self.event_id = event_id


def gen_background(n, points, days, start, used_plates, event_id_start):
    events = []
    event_id = event_id_start
    for _ in range(n):
        province, letters, digits, _ = new_plate(used_plates)
        n_trips = random.randint(1, 3)
        for _ in range(n_trips):
            pt = random.choice(points)
            day = random.randint(0, days - 1)
            t = start + timedelta(days=day, hours=random.uniform(0, 24))
            events.append(Event(province, letters, digits, pt["id"], t, "background", event_id))
        event_id += 1
    return events, event_id


def plant_routine_co_travel(points, days, start, used_plates, event_id_start):
    """Iki 'komsu' arac her gun ayni rotayi ayni saatte paylasir.

    Konvoy DEGIL: rutin, tek noktada degil ama HER GUN tekrar eden bir
    birlikte-seyahat kalibi. Konvoy tespiti trafik hacmine gore
    normalize edilmezse bunu yanlislikla konvoy olarak isaretler
    (bkz. CLAUDE.md 'Convoy detection normalised by traffic volume').
    """
    events = []
    event_id = event_id_start
    route = random.sample(points, k=2)
    plates = []
    for _ in range(2):
        province, letters, digits, text = new_plate(used_plates)
        plates.append(text)
        for day in range(days):
            t = start + timedelta(days=day, hours=random.uniform(7.9, 8.1))
            for i, pt in enumerate(route):
                if i > 0:
                    secs, _ = travel_seconds(route[i - 1], pt, 50.0)
                    t += timedelta(seconds=secs)
                events.append(Event(province, letters, digits, pt["id"], t, "routine_co_travel", event_id))
        event_id += 1
    truth = {
        "plates": plates,
        "points": [p["id"] for p in route],
        "label": "NOT a convoy — daily commute overlap, should be suppressed by traffic-volume normalisation",
    }
    return events, truth, event_id


def plant_convoy(points, days, start, used_plates, event_id_start):
    """3 arac, 3 farkli noktada, 2 ayri 'gorev' gununde birlikte gorunur.

    Gunluk tekrar eden bir commute degil (routine_co_travel'dan farki bu) —
    az sayida farkli noktada, dar zaman penceresinde birlikte gorulme.
    """
    events = []
    event_id = event_id_start
    convoy_points = random.sample(points, k=3)
    plates = []
    provinces = []
    for _ in range(3):
        province, letters, digits, text = new_plate(used_plates)
        plates.append(text)
        provinces.append((province, letters, digits))

    mission_days = random.sample(range(0, days), k=min(2, days))
    for day in mission_days:
        base = start + timedelta(days=day, hours=random.uniform(9, 15))
        for pi, pt in enumerate(convoy_points):
            pt_time = base + timedelta(minutes=pi * random.uniform(20, 40))
            for (province, letters, digits) in provinces:
                jitter = timedelta(minutes=random.uniform(0, 3))
                events.append(Event(province, letters, digits, pt["id"], pt_time + jitter, "convoy", event_id))
        event_id += 1
    truth = {
        "plates": plates,
        "points": [p["id"] for p in convoy_points],
        "missions": len(mission_days),
        "label": "planted convoy — co-occurs at 3 distinct points on 2 separate missions",
    }
    return events, truth, event_id


def plant_clone(points, days, start, used_plates, event_id_start):
    """Ayni plaka iki farkli noktada, aralarindaki mesafeye gore
    fiziksel olarak imkansiz bir hizda 'gorulur'."""
    p1, p2 = random.sample(points, k=2)
    dist = haversine_km(p1["enlem"], p1["boylam"], p2["enlem"], p2["boylam"])
    # imkansiz hiz icin gerekli sureden daha kisa bir bosluk sec
    max_seconds_for_impossible = dist / MAX_PLAUSIBLE_SPEED_KMH * 3600.0
    gap = timedelta(seconds=random.uniform(30, max(31, max_seconds_for_impossible * 0.6)))

    province, letters, digits, text = new_plate(used_plates)
    t1 = start + timedelta(days=random.randint(0, days - 1), hours=random.uniform(8, 18))
    t2 = t1 + gap
    event_id = event_id_start
    events = [
        Event(province, letters, digits, p1["id"], t1, "clone", event_id),
        Event(province, letters, digits, p2["id"], t2, "clone", event_id),
    ]
    required_speed = dist / (gap.total_seconds() / 3600.0)
    truth = {
        "plate": text,
        "occurrences": [
            {"nokta_id": p1["id"], "zaman": t1.isoformat()},
            {"nokta_id": p2["id"], "zaman": t2.isoformat()},
        ],
        "distance_km": round(dist, 2),
        "gap_seconds": gap.total_seconds(),
        "required_speed_kmh": round(required_speed, 1),
        "label": f"physically impossible ({required_speed:.0f} km/h > {MAX_PLAUSIBLE_SPEED_KMH:.0f} km/h max)",
    }
    return events, truth, event_id + 1


def plant_anomalies(commuter_specs, points, days, start, event_id_start):
    """Var olan commuter'lardan bir kacina, alisilmadik saat/nokta ekler."""
    events, truths = [], []
    event_id = event_id_start
    chosen = random.sample(commuter_specs, k=min(2, len(commuter_specs)))
    for province, letters, digits, route in chosen:
        anomaly_type = random.choice(["odd_hour", "odd_point"])
        if anomaly_type == "odd_hour":
            pt = random.choice(route)
            t = start + timedelta(days=random.randint(0, days - 1), hours=random.uniform(1, 4))  # gece yarisi
        else:
            pt = random.choice([p for p in points if p not in route])
            t = start + timedelta(days=random.randint(0, days - 1), hours=random.uniform(9, 17))
        events.append(Event(province, letters, digits, pt["id"], t, "anomaly", event_id))
        truths.append({
            "plate": f"{province}{letters}{digits}",
            "type": anomaly_type,
            "nokta_id": pt["id"],
            "zaman": t.isoformat(),
            "label": "odd_hour: gece yarisi bu arac icin alisilmadik"
                     if anomaly_type == "odd_hour"
                     else "odd_point: bu aracin rutin rotasinda olmayan nokta",
        })
        event_id += 1
    return events, truths, event_id


def build_watchlist(observed_plates, unused_used_plates, n_appear=3, n_absent=3):
    appearing = random.sample(list(observed_plates), k=min(n_appear, len(observed_plates)))
    absent = []
    used = set(observed_plates) | unused_used_plates
    for _ in range(n_absent):
        _, _, _, text = new_plate(used)
        absent.append(text)

    entries = []
    for plate in appearing:
        entries.append({"plaka": plate, "sebep": random.choice(WATCHLIST_REASONS), "appears": True})
    for plate in absent:
        entries.append({"plaka": plate, "sebep": random.choice(WATCHLIST_REASONS), "appears": False})
    return entries


@torch.no_grad()
def ocr_read(model, province, letters, digits, severity, width, height):
    img = render_clean_plate(province, letters, digits)
    img = harsh_degrade(img, severity)
    img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    tensor = torch.from_numpy(gray).unsqueeze(0).unsqueeze(0)
    log_probs = model(tensor)
    texts, confidences = greedy_decode_with_confidence(log_probs)
    return texts[0], confidences[0]


def apply_ocr_noise(events, model, severity, width, height, max_tries, critical_tags):
    """Her event'e gercek OCR checkpoint'inden gecirilmis bir okuma ekler.

    Format-gecersiz okumalar pipeline.py'nin yaptigi gibi elenir (retry ile).
    Planted (kritik) olaylar senaryo butunlugu icin daha fazla denenir; hala
    basarisizsa temiz metne dusulur (nadir, dusuk severity'de beklenmez).
    """
    rows = []
    n_dropped = 0
    for ev in events:
        tries = max_tries if ev.tag not in critical_tags else max_tries * 4
        text, conf, det_conf = None, None, random.uniform(0.85, 0.99)
        for _ in range(tries):
            cand_text, cand_conf = ocr_read(model, ev.province, ev.letters, ev.digits, severity, width, height)
            if parse_plate(cand_text) is not None:
                text, conf = cand_text, cand_conf
                break
        if text is None:
            if ev.tag in critical_tags:
                text, conf = ev.clean_plaka, 1.0
            else:
                n_dropped += 1
                continue
        rows.append({
            "plaka": text,
            "nokta_id": ev.nokta_id,
            "zaman": ev.zaman.isoformat(),
            "guven": round(det_conf * conf, 4),
            "arac_tipi": "unknown",
            "clean_plaka": ev.clean_plaka,
            "event_tag": ev.tag,
            "event_id": ev.event_id,
        })
    return rows, n_dropped


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_into_db(points, rows, watchlist):
    from app.db import SessionLocal
    from app.models import ArananArac, GecisKaydi, Nokta

    db = SessionLocal()
    id_map = {}
    for p in points:
        nokta = Nokta(ad=p["ad"], enlem=p["enlem"], boylam=p["boylam"])
        db.add(nokta)
        db.flush()
        id_map[p["id"]] = nokta.id

    for row in rows:
        db.add(GecisKaydi(
            plaka=row["plaka"],
            nokta_id=id_map[row["nokta_id"]],
            zaman=datetime.fromisoformat(row["zaman"]),
            guven=row["guven"],
            arac_tipi=row["arac_tipi"],
        ))

    for entry in watchlist:
        exists = db.query(ArananArac).filter_by(plaka=entry["plaka"]).first()
        if not exists:
            db.add(ArananArac(plaka=entry["plaka"], sebep=entry["sebep"]))

    db.commit()
    db.close()
    return id_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/scenario")
    parser.add_argument("--n-points", type=int, default=10)
    parser.add_argument("--n-commuters", type=int, default=15)
    parser.add_argument("--n-background", type=int, default=150)
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--severity", type=float, default=0.2,
                        help="eval_ocr.harsh_degrade siddeti (0=temiz, 1=en kotu). "
                             "CLAUDE.md gerceki severity 0.0-0.3 araligini 'gercekci' sayiyor.")
    parser.add_argument("--ocr-checkpoint", default="runs/ocr/plate_ocr/best.pt")
    parser.add_argument("--width", type=int, default=192)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--load-db", action="store_true",
                        help="CSV'lere ek olarak dogrudan veritabanina yaz")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    os.makedirs(args.out, exist_ok=True)

    print("Nokta topolojisi kuruluyor...")
    points = generate_points(args.n_points)

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=args.days)

    used_plates = set()
    all_events = []
    event_id = 1

    print(f"{args.n_commuters} duzenli gidip-gelen arac uretiliyor ({args.days} gun)...")
    commuter_specs = []
    for _ in range(args.n_commuters):
        route = random.sample(points, k=random.choice([2, 2, 3]))
        province, letters, digits, _ = new_plate(used_plates)
        commuter_specs.append((province, letters, digits, route))
    for province, letters, digits, route in commuter_specs:
        for day in range(args.days):
            day_start = start + timedelta(days=day)
            t = day_start + timedelta(hours=random.uniform(7, 9))
            for i, pt in enumerate(route):
                if i > 0:
                    secs, _ = travel_seconds(route[i - 1], pt, random.uniform(35, 75))
                    t += timedelta(seconds=secs + random.uniform(-120, 120))
                all_events.append(Event(province, letters, digits, pt["id"], t, "commuter", event_id))
            if random.random() < 0.8:
                t = day_start + timedelta(hours=random.uniform(17, 19))
                rev = list(reversed(route))
                for i, pt in enumerate(rev):
                    if i > 0:
                        secs, _ = travel_seconds(rev[i - 1], pt, random.uniform(35, 75))
                        t += timedelta(seconds=secs + random.uniform(-120, 120))
                    all_events.append(Event(province, letters, digits, pt["id"], t, "commuter", event_id))
        event_id += 1

    print(f"{args.n_background} arka plan (tek seferlik) arac uretiliyor...")
    bg_events, event_id = gen_background(args.n_background, points, args.days, start, used_plates, event_id)
    all_events += bg_events

    print("Rutin birlikte-seyahat (konvoy DEGIL, yanlis pozitif tuzagi) ekleniyor...")
    routine_events, routine_truth, event_id = plant_routine_co_travel(
        points, args.days, start, used_plates, event_id)
    all_events += routine_events

    print("Konvoy ekleniyor...")
    convoy_events, convoy_truth, event_id = plant_convoy(points, args.days, start, used_plates, event_id)
    all_events += convoy_events

    print("Klonlanmis plaka ekleniyor...")
    clone_events, clone_truth, event_id = plant_clone(points, args.days, start, used_plates, event_id)
    all_events += clone_events

    print("Rota/zaman anomalileri ekleniyor...")
    anomaly_events, anomaly_truths, event_id = plant_anomalies(commuter_specs, points, args.days, start, event_id)
    all_events += anomaly_events

    all_events.sort(key=lambda e: e.zaman)

    print(f"OCR gurultusu enjekte ediliyor (severity={args.severity}, "
          f"{len(all_events)} okuma, checkpoint={args.ocr_checkpoint})...")
    model = load_model(args.ocr_checkpoint)
    critical_tags = {"convoy", "clone", "routine_co_travel", "anomaly"}
    rows, n_dropped = apply_ocr_noise(
        all_events, model, args.severity, args.width, args.height,
        max_tries=3, critical_tags=critical_tags,
    )
    print(f"  {len(rows)} gecerli-format okuma yazildi, {n_dropped} gecersiz-format okuma elendi "
          f"(pipeline.py'nin gercek davranisiyla ayni).")

    observed_plates = {r["clean_plaka"] for r in rows}
    watchlist = build_watchlist(observed_plates, used_plates)

    write_csv(os.path.join(args.out, "nokta.csv"), points, ["id", "ad", "enlem", "boylam"])
    write_csv(os.path.join(args.out, "gecis_kaydi.csv"), rows,
              ["plaka", "nokta_id", "zaman", "guven", "arac_tipi",
               "clean_plaka", "event_tag", "event_id"])
    write_csv(os.path.join(args.out, "aranan_arac.csv"), watchlist, ["plaka", "sebep", "appears"])

    ground_truth = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": vars(args),
        "points": points,
        "convoy": convoy_truth,
        "routine_co_travel": routine_truth,
        "cloned_plate": clone_truth,
        "anomalies": anomaly_truths,
        "watchlist": watchlist,
        "stats": {
            "total_events": len(all_events),
            "rows_written": len(rows),
            "rows_dropped_invalid_format": n_dropped,
            "unique_plates": len(used_plates),
        },
    }
    with open(os.path.join(args.out, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, ensure_ascii=False, indent=2)

    print(f"\nBitti. Cikti -> {args.out}/")
    print(f"  nokta.csv, gecis_kaydi.csv, aranan_arac.csv, ground_truth.json")

    if args.load_db:
        print("Veritabanina yaziliyor...")
        load_into_db(points, rows, watchlist)
        print("  Yazildi.")


if __name__ == "__main__":
    main()
