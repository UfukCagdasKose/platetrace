"""OCR modelini artan bozulma siddetinde degerlendirir.

train_ocr.py'daki val_exact rakami, egitimle ayni bozulma araligindan
gelen bir val split'i olctugu icin 100'e cok yakin cikabilir (bkz.
runs/ocr/plate_ocr egitim ciktisi). Bu, modelin sentetik gorevi cozdugunu
gosterir, gercek kamera kosullarina hazir oldugunu degil.

Bu script tools/synth_plates.py'nin bozulma fonksiyonlarini severity
parametresiyle sertlestirerek modelin nerede kirildigini olcer — CLAUDE.md'de
tarif edilen "kontrollu bozulma deneyi" fikrinin ilk adimi.

Kullanim:
    python3 eval_ocr.py --checkpoint runs/ocr/plate_ocr/best.pt
"""

import argparse
import random
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, "tools")
from synth_plates import (apply_motion_blur, apply_perspective, apply_shadow,
                          random_plate_text, render_clean_plate)
from train_ocr import CHARS, CRNN, greedy_decode, levenshtein


def harsh_degrade(img, severity):
    """degrade()'in siddet kadranli hali. severity in [0, 1], 1 = en kotu."""
    img = apply_perspective(img, strength=0.05 + 0.25 * severity)
    if random.random() < 0.7:
        img = apply_shadow(img)

    alpha = random.uniform(1 - 0.6 * severity, 1 + 0.6 * severity)
    beta = random.uniform(-60 * severity, 60 * severity)
    img = np.clip(img * alpha + beta, 0, 255).astype(np.uint8)

    h, w = img.shape[:2]
    scale = (random.uniform(0.12, 0.35) if severity > 0.5
             else random.uniform(0.3, 0.9))
    small = cv2.resize(img, (max(6, int(w * scale)), max(3, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    img = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    if random.random() < 0.8:
        img = apply_motion_blur(img, ksize=random.choice([5, 7, 9, 11, 13]))
    if random.random() < 0.6:
        img = cv2.GaussianBlur(img, (0, 0), sigmaX=random.uniform(1.0, 3.5))

    noise = np.random.normal(0, random.uniform(5, 10 + 25 * severity), img.shape)
    img = np.clip(img + noise, 0, 255).astype(np.uint8)

    quality = random.randint(10, max(11, int(60 - 40 * severity)))
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if ok:
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return img


def load_model(checkpoint_path):
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    model = CRNN(num_classes=len(ckpt["chars"]))
    model.load_state_dict(ckpt["model"])
    model.eval()
    return model


@torch.no_grad()
def evaluate_severity(model, severity, n, width, height):
    exact, char_err, char_total = 0, 0, 0
    for _ in range(n):
        province, letters, digits = random_plate_text()
        text = f"{province}{letters}{digits}"
        img = render_clean_plate(province, letters, digits)
        img = harsh_degrade(img, severity)
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        tensor = torch.from_numpy(gray).unsqueeze(0).unsqueeze(0)

        log_probs = model(tensor)
        pred = greedy_decode(log_probs)[0]

        exact += int(pred == text)
        char_err += levenshtein(pred, text)
        char_total += len(text)
    return exact / n, 1 - char_err / char_total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="runs/ocr/plate_ocr/best.pt")
    parser.add_argument("--n", type=int, default=300,
                        help="siddet basina ornek sayisi")
    parser.add_argument("--width", type=int, default=192)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--severities", type=float, nargs="+",
                        default=[0.0, 0.3, 0.6, 0.8, 1.0])
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    model = load_model(args.checkpoint)

    print(f"{'severity':>8}  {'exact':>7}  {'char_acc':>8}")
    for severity in args.severities:
        exact_acc, char_acc = evaluate_severity(
            model, severity, args.n, args.width, args.height,
        )
        print(f"{severity:>8.1f}  {exact_acc:>7.3f}  {char_acc:>8.3f}")


if __name__ == "__main__":
    main()
