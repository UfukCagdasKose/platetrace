"""Plaka tespiti icin YOLO fine-tune.

Once Roboflow Universe'ten bir plaka veri seti indir (YOLOv8 formatinda,
data/plates/ altina), sonra (YOLO26 agirligi otomatik indirilir):

    python3 train_detector.py --data data/plates/data.yaml --epochs 30

Mac'te MPS, GPU'lu makinede cuda, digerinde cpu otomatik secilir.
"""

import argparse

import torch
from ultralytics import YOLO


def pick_device():
    if torch.cuda.is_available():
        return 0
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/plates/data.yaml")
    parser.add_argument("--model", default="yolo26n.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--name", default="plate_detector")
    args = parser.parse_args()

    device = pick_device()
    print(f"Device: {device}")

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        name=args.name,
        patience=10,
        plots=True,
    )

    metrics = model.val()
    print(f"mAP50    : {metrics.box.map50:.4f}")
    print(f"mAP50-95 : {metrics.box.map:.4f}")


if __name__ == "__main__":
    main()
