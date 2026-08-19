"""Türk plakası sentetik veri üreteci.

OCR eğitimi için etiketli plaka görseli üretir. Gerçek plaka verisi
kullanmadan, ölçülebilir bir OCR modeli eğitmeyi mümkün kılar.

Kullanım:
    python3 tools/synth_plates.py --count 20000 --out data/synth_plates
    python3 tools/synth_plates.py --count 50 --out data/preview --clean

Çıktı:
    <out>/images/000001.png ...
    <out>/labels.txt        -> "images/000001.png\t34ABC123" formatında
"""

import argparse
import os
import random
import string

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Türk plaka formatı: il kodu (01-81) + harf/rakam grubu.
# Harf sayısına göre izin verilen rakam sayısı:
#   1 harf -> 4 veya 5 rakam
#   2 harf -> 3 veya 4 rakam
#   3 harf -> 2 rakam
LETTER_DIGIT_RULES = {1: (4, 5), 2: (3, 4), 3: (2, 2)}

# Plakada kullanılmayan harfler (Türkçe'ye özgü karakterler plakada yok).
PLATE_LETTERS = [c for c in string.ascii_uppercase if c not in "QWX"]

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",                          # Windows
]


def find_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    print("UYARI: TrueType font bulunamadi, PIL varsayilan fontu kullaniliyor. "
          "Gorseller gercekci olmayacak. FONT_CANDIDATES listesine kendi "
          "font yolunu ekle.")
    return ImageFont.load_default()


def random_plate_text():
    province = f"{random.randint(1, 81):02d}"
    n_letters = random.choice([1, 2, 3])
    lo, hi = LETTER_DIGIT_RULES[n_letters]
    n_digits = random.randint(lo, hi)
    letters = "".join(random.choice(PLATE_LETTERS) for _ in range(n_letters))
    digits = "".join(random.choice(string.digits) for _ in range(n_digits))
    return province, letters, digits


def render_clean_plate(province, letters, digits, width=520, height=110):
    """Bozulma uygulanmamis, duz plaka gorseli uretir."""
    img = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    # Kenarlik
    draw.rectangle([0, 0, width - 1, height - 1], outline=(20, 20, 20), width=3)

    # Sol mavi serit ("TR")
    strip_w = int(width * 0.085)
    draw.rectangle([3, 3, strip_w, height - 4], fill=(0, 45, 130))
    small_font = find_font(int(height * 0.28))
    draw.text((strip_w * 0.28, height * 0.55), "TR", font=small_font,
              fill=(255, 255, 255))

    text = f"{province} {letters} {digits}"
    font = find_font(int(height * 0.62))

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = strip_w + (width - strip_w - text_w) / 2
    y = (height - text_h) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=(15, 15, 15))

    # PIL RGB -> OpenCV BGR
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def apply_perspective(img, strength=0.12):
    h, w = img.shape[:2]
    d = strength * min(h, w)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [random.uniform(0, d), random.uniform(0, d)],
        [w - random.uniform(0, d), random.uniform(0, d)],
        [w - random.uniform(0, d), h - random.uniform(0, d)],
        [random.uniform(0, d), h - random.uniform(0, d)],
    ])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, matrix, (w, h),
                               borderMode=cv2.BORDER_REPLICATE)


def apply_motion_blur(img, ksize):
    kernel = np.zeros((ksize, ksize), dtype=np.float32)
    angle = random.uniform(0, np.pi)
    cx = cy = ksize // 2
    for i in range(ksize):
        offset = i - cx
        x = int(round(cx + offset * np.cos(angle)))
        y = int(round(cy + offset * np.sin(angle)))
        if 0 <= x < ksize and 0 <= y < ksize:
            kernel[y, x] = 1.0
    kernel /= kernel.sum()
    return cv2.filter2D(img, -1, kernel)


def apply_shadow(img):
    h, w = img.shape[:2]
    overlay = np.ones((h, w), dtype=np.float32)
    x1, x2 = sorted(random.sample(range(w), 2))
    overlay[:, x1:x2] = random.uniform(0.45, 0.8)
    overlay = cv2.GaussianBlur(overlay, (0, 0), sigmaX=w * 0.05)
    return np.clip(img * overlay[:, :, None], 0, 255).astype(np.uint8)


def degrade(img):
    """Gercek kamera kosullarini taklit eden bozulmalar."""
    img = apply_perspective(img, strength=random.uniform(0.02, 0.14))

    if random.random() < 0.4:
        img = apply_shadow(img)

    # Parlaklik / kontrast
    alpha = random.uniform(0.6, 1.4)   # kontrast
    beta = random.uniform(-45, 45)     # parlaklik
    img = np.clip(img * alpha + beta, 0, 255).astype(np.uint8)

    # Cozunurluk kaybi: kucult, sonra geri buyut
    h, w = img.shape[:2]
    scale = random.uniform(0.25, 0.9)
    small = cv2.resize(img, (max(8, int(w * scale)), max(4, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    img = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    if random.random() < 0.5:
        img = apply_motion_blur(img, ksize=random.choice([3, 5, 7, 9]))

    if random.random() < 0.3:
        img = cv2.GaussianBlur(img, (0, 0), sigmaX=random.uniform(0.5, 2.0))

    # Gurultu
    noise = np.random.normal(0, random.uniform(2, 14), img.shape)
    img = np.clip(img + noise, 0, 255).astype(np.uint8)

    # JPEG artefakti
    quality = random.randint(25, 90)
    ok, buf = cv2.imencode(".jpg", img,
                           [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if ok:
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20000)
    parser.add_argument("--out", default="data/synth_plates")
    parser.add_argument("--width", type=int, default=192)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true",
                        help="Bozulma uygulama (gorsel kontrol icin)")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    images_dir = os.path.join(args.out, "images")
    os.makedirs(images_dir, exist_ok=True)
    labels_path = os.path.join(args.out, "labels.txt")

    with open(labels_path, "w", encoding="utf-8") as labels_file:
        for i in range(args.count):
            province, letters, digits = random_plate_text()
            plate = render_clean_plate(province, letters, digits)
            if not args.clean:
                plate = degrade(plate)
            plate = cv2.resize(plate, (args.width, args.height),
                               interpolation=cv2.INTER_AREA)

            name = f"{i:06d}.png"
            cv2.imwrite(os.path.join(images_dir, name), plate)
            labels_file.write(f"images/{name}\t{province}{letters}{digits}\n")

            if (i + 1) % 2000 == 0:
                print(f"{i + 1}/{args.count}")

    print(f"Bitti. {args.count} gorsel -> {args.out}")
    print(f"Etiketler -> {labels_path}")


if __name__ == "__main__":
    main()
