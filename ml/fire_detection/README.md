# Fire Detection — model + training + inference

See [`docs/30-ml-stack.md`](../../docs/30-ml-stack.md) for the full ML strategy.

## What ships in this directory

- `train.py` — entrypoint for FASDD pretrain + FLAME-2 fine-tune.
- `infer.py` — Jetson-side inference loop, MAVLink + camera fusion, signal emit.
- `MODEL_CARD.md` — to be authored at first stable release.
- `requirements.txt` — pinned (ultralytics, onnx, tensorrt, opencv-python, pymavlink).

## Model

- Base: `yolov8n.pt` (Ultralytics).
- Pretrain dataset: FASDD (Flame and Smoke Detection Dataset, ~120k images).
- Fine-tune: FLAME / FLAME-2 (UAV viewpoint, RGB + thermal palettes).
- Eval: D-Fire holdout + custom zone set.
- Export: TensorRT FP16 engine, `wildfire_yolo_v{version}.engine`.

## Training (operator's RTX 5070 Ti)

```bash
# On Windows PC at 100.71.10.48
cd E:\Sapphire\Code\wildfire-watch\ml\fire_detection
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

python train.py \
  --base yolov8n.pt \
  --data fasdd_cv.yaml \
  --epochs 100 --imgsz 640 --batch 32 --device 0
```

Expected wall time: ~6 h on 5070 Ti at 16 GB VRAM.

## Inference (Jetson Orin Nano Super)

```bash
# On drone Jetson
python infer.py \
  --engine wildfire_yolo_v0.3.engine \
  --rgb_device /dev/video0 \
  --thermal_device /dev/video1 \
  --mavlink_url udp:127.0.0.1:14550 \
  --signal_endpoint http://100.67.171.79:18081/signal \
  --confidence_threshold 0.65 \
  --auto_loiter_threshold 0.85
```

## Multimodal fusion

The signal-emit gate is implemented in `infer.py::should_emit()`:

```python
def should_emit(rgb_score, thermal_delta_c, persistence_frames, geofence_ok, wind_consistent):
    return (
        rgb_score >= 0.6
        and thermal_delta_c >= 5.0
        and persistence_frames >= 5
        and geofence_ok
        and wind_consistent
    )
```

## Geolocation of detected target

Given the drone's position, attitude, camera FOV, and the bounding-box pixel
coords, we estimate the target's lat/lon by ray-casting from the camera's
optical axis to the ground (or a DEM). See `infer.py::pixel_to_geo()`.
