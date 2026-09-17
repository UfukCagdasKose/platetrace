"""Plaka OCR icin CRNN (CNN + BiLSTM) + CTC egitimi.

Once sentetik veri uret (tools/synth_plates.py), sonra:

    python3 train_ocr.py --data data/synth_plates --epochs 30

Mac'te MPS, GPU'lu makinede cuda, digerinde cpu otomatik secilir.

Etiket formati (synth_plates.py ciktisi): "images/000001.png\t34ABC123"
Karakter seti sentetik uretecinkiyle ayni: rakamlar + Q/W/X disi harfler,
il kodu da rakam oldugu icin ek karaktere gerek yok.
"""

import argparse
import os
import random
import string

# MPS henuz aten::_ctc_loss'u desteklemiyor; bu tek op icin CPU'ya
# otomatik dusmeyi ac (torch import edilmeden once ayarlanmali).
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

CHARS = "0123456789" + "".join(c for c in string.ascii_uppercase if c not in "QWX")
CHAR2IDX = {c: i + 1 for i, c in enumerate(CHARS)}  # 0 = CTC blank
IDX2CHAR = {i + 1: c for i, c in enumerate(CHARS)}


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_labels(data_dir):
    labels_path = os.path.join(data_dir, "labels.txt")
    samples = []
    with open(labels_path, encoding="utf-8") as f:
        for line in f:
            rel_path, text = line.rstrip("\n").split("\t")
            samples.append((os.path.join(data_dir, rel_path), text))
    return samples


class PlateOCRDataset(Dataset):
    def __init__(self, samples, width, height):
        self.samples = samples
        self.width = width
        self.height = height

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, text = self.samples[idx]
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        img = cv2.resize(img, (self.width, self.height), interpolation=cv2.INTER_AREA)
        img = img.astype(np.float32) / 255.0
        img = torch.from_numpy(img).unsqueeze(0)  # (1, H, W)
        target = torch.tensor([CHAR2IDX[c] for c in text], dtype=torch.long)
        return img, target, text


def collate_fn(batch):
    images, targets, texts = zip(*batch)
    images = torch.stack(images)
    target_lengths = torch.tensor([len(t) for t in targets], dtype=torch.long)
    targets = torch.cat(targets)
    return images, targets, target_lengths, texts


class CRNN(nn.Module):
    """Kucuk CNN govde + BiLSTM + CTC cikisi.

    Yukseklik CNN icinde 1'e indirilir, genislik CTC zaman eksenine
    (karakter sekansina) karsilik gelir.
    """

    def __init__(self, num_classes):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1)),
            nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, None)),  # yukseklik -> 1, genislik korunur
        )
        self.rnn = nn.LSTM(128, 256, num_layers=2, bidirectional=True, batch_first=True)
        self.fc = nn.Linear(512, num_classes + 1)  # +1 = CTC blank

    def forward(self, x):
        feat = self.cnn(x)              # (B, C, 1, W')
        feat = feat.squeeze(2)          # (B, C, W')
        feat = feat.permute(0, 2, 1)    # (B, W', C)
        seq, _ = self.rnn(feat)         # (B, W', 512)
        out = self.fc(seq)              # (B, W', num_classes+1)
        return out.log_softmax(2)


def greedy_decode(log_probs):
    """log_probs: (B, T, num_classes+1) -> list[str], en olasi yol + tekrar/blank temizligi."""
    preds = log_probs.argmax(2).cpu().numpy()  # (B, T)
    texts = []
    for row in preds:
        chars = []
        prev = 0
        for idx in row:
            if idx != 0 and idx != prev:
                chars.append(IDX2CHAR[idx])
            prev = idx
        texts.append("".join(chars))
    return texts


def greedy_decode_with_confidence(log_probs):
    """greedy_decode ile ayni yolu izler, ayrica secilen her karakterin
    olasiligindan bir guven skoru (0-1) uretir. Gecis kaydina yazilacak
    guven degeri icin kullanilir."""
    probs = log_probs.exp().cpu().numpy()   # (B, T, C)
    preds = probs.argmax(2)                 # (B, T)
    texts, confidences = [], []
    for row_idx, row in enumerate(preds):
        chars, char_probs = [], []
        prev = 0
        for t, idx in enumerate(row):
            if idx != 0 and idx != prev:
                chars.append(IDX2CHAR[idx])
                char_probs.append(probs[row_idx, t, idx])
            prev = idx
        texts.append("".join(chars))
        confidences.append(float(np.mean(char_probs)) if char_probs else 0.0)
    return texts, confidences


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    exact, total, char_errs, char_total = 0, 0, 0, 0
    for images, targets, target_lengths, texts in loader:
        images = images.to(device)
        log_probs = model(images)
        preds = greedy_decode(log_probs)
        for pred, gt in zip(preds, texts):
            total += 1
            exact += int(pred == gt)
            char_errs += levenshtein(pred, gt)
            char_total += len(gt)
    return exact / total, 1 - char_errs / char_total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/synth_plates")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--width", type=int, default=192)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--name", default="plate_ocr")
    args = parser.parse_args()

    random.seed(args.seed)
    device = pick_device()
    print(f"Device: {device}")

    samples = load_labels(args.data)
    random.shuffle(samples)
    n_val = int(len(samples) * args.val_split)
    val_samples, train_samples = samples[:n_val], samples[n_val:]
    print(f"Train: {len(train_samples)}  Val: {len(val_samples)}")

    train_loader = DataLoader(
        PlateOCRDataset(train_samples, args.width, args.height),
        batch_size=args.batch, shuffle=True, collate_fn=collate_fn,
    )
    val_loader = DataLoader(
        PlateOCRDataset(val_samples, args.width, args.height),
        batch_size=args.batch, shuffle=False, collate_fn=collate_fn,
    )

    model = CRNN(num_classes=len(CHARS)).to(device)
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    out_dir = os.path.join("runs", "ocr", args.name)
    os.makedirs(out_dir, exist_ok=True)
    best_acc = 0.0

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for images, targets, target_lengths, _ in train_loader:
            images = images.to(device)
            targets = targets.to(device)

            log_probs = model(images)                     # (B, T, C)
            input_lengths = torch.full(
                (images.size(0),), log_probs.size(1), dtype=torch.long,
            )
            loss = criterion(
                log_probs.permute(1, 0, 2), targets, input_lengths, target_lengths,
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * images.size(0)

        train_loss = total_loss / len(train_samples)
        exact_acc, char_acc = evaluate(model, val_loader, device)
        print(f"epoch {epoch:02d}/{args.epochs}  loss {train_loss:.4f}  "
              f"val_exact {exact_acc:.4f}  val_char_acc {char_acc:.4f}")

        if exact_acc > best_acc:
            best_acc = exact_acc
            torch.save(
                {"model": model.state_dict(), "chars": CHARS},
                os.path.join(out_dir, "best.pt"),
            )

    print(f"Bitti. En iyi val exact-match dogrulugu: {best_acc:.4f}")
    print(f"Agirlik -> {os.path.join(out_dir, 'best.pt')}")


if __name__ == "__main__":
    main()
