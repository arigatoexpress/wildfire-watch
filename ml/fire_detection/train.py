"""wildfire-watch — fire/smoke detector training entrypoint.

Pretrain on FASDD, fine-tune on FLAME-2 (UAV palettes), eval on D-Fire.

Run:
    python train.py --base yolov8n.pt --data fasdd_cv.yaml --epochs 100

Skeleton — fill in dataset YAML wiring + W&B logging once datasets are downloaded.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train wildfire-watch fire/smoke detector.")
    p.add_argument("--base", default="yolov8n.pt", help="Base weights to fine-tune.")
    p.add_argument("--data", default="fasdd_cv.yaml", help="Ultralytics data YAML.")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--device", default="0", help="CUDA device id or 'cpu'.")
    p.add_argument("--project", default="runs/train", help="Output dir.")
    p.add_argument("--name", default="wildfire_yolo", help="Run name.")
    p.add_argument("--export-trt", action="store_true",
                   help="After training, export TensorRT FP16 engine.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Lazy import so --help works without ultralytics installed.
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise SystemExit("Install dependencies: pip install -r requirements.txt") from e

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(
            f"Data YAML {data_path} not found. "
            "See ml/fire_detection/README.md for dataset prep."
        )

    model = YOLO(args.base)
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        patience=20,
        cos_lr=True,
        amp=True,
    )

    print(f"Training complete. Best weights: {results.save_dir}/weights/best.pt")

    if args.export_trt:
        # Export TensorRT FP16 engine for Jetson deployment.
        model.export(format="engine", half=True, device=args.device)
        print("TensorRT engine exported to weights/best.engine")


if __name__ == "__main__":
    main()
