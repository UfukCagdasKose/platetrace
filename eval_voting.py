"""Track-level karakter oylamasinin tek-kare OCR'a karsi kazancini olcer.

Gercek video/ByteTrack henuz yok, ama track'in ne yaptigini simule etmek
kolay: ayni plakayi N kere, her seferinde bagimsiz bozulmayla OCR'dan
gecir (eval_ocr.py'nin bozulma fonksiyonu), sonra voting.vote_plate ile
tek plakaya indir. Tek kare dogrulugu ile oylanmis dogrulugu karsilastirir.

Kullanim:
    python3 eval_voting.py --checkpoint runs/ocr/plate_ocr/best.pt
"""

import argparse
import random
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, "tools")
from synth_plates import random_plate_text, render_clean_plate
from eval_ocr import harsh_degrade, load_model
from train_ocr import greedy_decode
from voting import vote_plate


@torch.no_grad()
def read_frame(model, img, width, height):
    img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    tensor = torch.from_numpy(gray).unsqueeze(0).unsqueeze(0)
    log_probs = model(tensor)
    return greedy_decode(log_probs)[0]


def simulate_track(model, province, letters, digits, n_frames,
                    severity, width, height):
    reads = []
    for _ in range(n_frames):
        img = render_clean_plate(province, letters, digits)
        img = harsh_degrade(img, severity)
        reads.append(read_frame(model, img, width, height))
    return reads


def evaluate(model, severity, n_frames, n_tracks, width, height):
    single_correct, voted_correct = 0, 0
    for _ in range(n_tracks):
        province, letters, digits = random_plate_text()
        text = f"{province}{letters}{digits}"

        reads = simulate_track(model, province, letters, digits,
                               n_frames, severity, width, height)

        single_correct += int(reads[0] == text)
        voted_correct += int(vote_plate(reads) == text)

    return single_correct / n_tracks, voted_correct / n_tracks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="runs/ocr/plate_ocr/best.pt")
    parser.add_argument("--n-tracks", type=int, default=300,
                        help="siddet basina simule edilen track sayisi")
    parser.add_argument("--n-frames", type=int, default=15,
                        help="track basina kare sayisi")
    parser.add_argument("--width", type=int, default=192)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--severities", type=float, nargs="+",
                        default=[0.3, 0.6, 0.8, 1.0])
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    model = load_model(args.checkpoint)

    print(f"{'severity':>8}  {'single-frame':>13}  {'voted':>7}  {'gain':>6}")
    for severity in args.severities:
        single_acc, voted_acc = evaluate(
            model, severity, args.n_frames, args.n_tracks, args.width, args.height,
        )
        gain = voted_acc - single_acc
        print(f"{severity:>8.1f}  {single_acc:>13.3f}  {voted_acc:>7.3f}  {gain:>+6.3f}")


if __name__ == "__main__":
    main()
