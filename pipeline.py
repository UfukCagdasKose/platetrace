"""Tespit + OCR'i tek hatta birlestirip gecis kayitlarini veritabanina yazar.

Video ya da tek tek goruntulerden (--source bir video dosyasi ya da
goruntu klasoru olabilir) plaka tespit eder (train_detector.py agirligi),
her tespiti keser, OCR ile okur (train_ocr.py agirligi), Turk plaka
formatina uymayan okumalari eler, gecerli olanlari GecisKaydi olarak
veritabanina yazar.

    python3 pipeline.py --source data/plates/images/val --nokta-id 1 --dry-run
    python3 pipeline.py --source data/plates/images/val --nokta-id 1

Henuz ByteTrack yok: her tespit tek kareden okunuyor, track-level oylama
(voting.py) burada devrede degil — track'ler var oldugunda bu script'in
tespit/OCR kismi ayni kalir, aradaki fark her track icin coklu okumayi
vote_plate()'e gecirmek olur.

Bilinen sinirlar:
  - Perspektif duzeltmesi yok, kirpim dogrudan YOLO kutusu.
  - Tespit modeli sadece "plate" sinifini biliyor (data/plates/data.yaml),
    arac tipi tespiti yok -> arac_tipi hep "unknown" yazilir.
  - Goruntu klasoru modunda gercek zaman damgasi yok, isleme ani yazilir.
  - Tespit modeli gercek fotograflarla, OCR modeli sentetik veriyle
    egitildi; aralarinda alan (domain) farki var, dogruluk bu yuzden
    eval_ocr.py'daki sentetik egriden dusuk cikabilir.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import torch
from ultralytics import YOLO

sys.path.insert(0, "tools")
from synth_plates import LETTER_DIGIT_RULES, PLATE_LETTERS
from train_ocr import CHARS, CRNN, greedy_decode_with_confidence

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def parse_plate(text):
    """Metni (il_kodu, harfler, rakamlar) olarak ayirir; format uymuyorsa None.

    tools/synth_plates.py'deki uretim kurallariyla ayni: il kodu 01-81,
    harf sayisina gore izinli rakam araligi LETTER_DIGIT_RULES'ta.
    """
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


def load_ocr(checkpoint_path, device):
    ckpt = torch.load(checkpoint_path, map_location=device)
    model = CRNN(num_classes=len(ckpt["chars"]))
    model.load_state_dict(ckpt["model"])
    model.to(device).eval()
    return model


@torch.no_grad()
def read_plate(ocr_model, crop, device, width=192, height=64):
    img = cv2.resize(crop, (width, height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    tensor = torch.from_numpy(gray).unsqueeze(0).unsqueeze(0).to(device)
    log_probs = ocr_model(tensor)
    texts, confidences = greedy_decode_with_confidence(log_probs)
    return texts[0], confidences[0]


def iter_frames(source):
    """(frame_bgr, zaman) ciftleri uretir. Klasorse dosya sirasi, videoysa kare sirasi."""
    if os.path.isdir(source):
        for name in sorted(os.listdir(source)):
            if name.lower().endswith(IMAGE_EXTS):
                img = cv2.imread(os.path.join(source, name))
                if img is not None:
                    yield img, datetime.now(timezone.utc)
        return

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video acilamadi: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    start = datetime.now(timezone.utc)
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        yield frame, start + timedelta(seconds=frame_idx / fps)
        frame_idx += 1
    cap.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True,
                        help="Video dosyasi ya da goruntu klasoru")
    parser.add_argument("--detector-weights",
                        default="runs/detect/plate_detector/weights/best.pt")
    parser.add_argument("--ocr-weights", default="runs/ocr/plate_ocr/best.pt")
    parser.add_argument("--nokta-id", type=int, required=True)
    parser.add_argument("--det-conf", type=float, default=0.5,
                        help="YOLO tespiti icin minimum guven")
    parser.add_argument("--limit", type=int, default=None,
                        help="En fazla islenecek kare sayisi")
    parser.add_argument("--dry-run", action="store_true",
                        help="Veritabanina yazma, sadece yazdir")
    args = parser.parse_args()

    device = pick_device()
    print(f"Device: {device}")

    detector = YOLO(args.detector_weights)
    ocr_model = load_ocr(args.ocr_weights, device)

    if not args.dry_run:
        from app.db import SessionLocal
        from app.models import GecisKaydi
        db = SessionLocal()

    n_frames, n_detections, n_valid, n_invalid = 0, 0, 0, 0

    for frame_idx, (frame, zaman) in enumerate(iter_frames(args.source)):
        if args.limit is not None and frame_idx >= args.limit:
            break
        n_frames += 1

        result = detector.predict(frame, conf=args.det_conf, verbose=False)[0]
        for box in result.boxes:
            n_detections += 1
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            det_conf = float(box.conf[0])
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            if crop.size == 0:
                continue

            text, ocr_conf = read_plate(ocr_model, crop, device)
            parsed = parse_plate(text)
            if parsed is None:
                n_invalid += 1
                print(f"  [red] kare {frame_idx}: '{text}' gecersiz format, atlandi")
                continue

            n_valid += 1
            guven = det_conf * ocr_conf
            print(f"  [ok] kare {frame_idx}: {text}  guven={guven:.3f}")

            if not args.dry_run:
                db.add(GecisKaydi(
                    plaka=text,
                    nokta_id=args.nokta_id,
                    zaman=zaman,
                    guven=guven,
                    arac_tipi="unknown",
                ))

    if not args.dry_run:
        db.commit()
        db.close()

    print(f"\nKare: {n_frames}  Tespit: {n_detections}  "
          f"Gecerli: {n_valid}  Gecersiz format: {n_invalid}")
    if not args.dry_run:
        print(f"{n_valid} gecis kaydi veritabanina yazildi.")


if __name__ == "__main__":
    main()
