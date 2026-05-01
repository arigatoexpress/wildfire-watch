# Wildlife Identification — MegaDetector v6 + BirdNET

## Stack

- **Visual detection**: MegaDetector v6 Compact (`MDV6-yolov10-c`). 2% the
  parameter count of MDV5, better recall. ONNX → TensorRT FP16 on Jetson.
- **Species classification (downstream)**: PyTorch-Wildlife / SpeciesNet for
  flagged frames. Runs at ground station / Sapphire mesh, not on edge.
- **Audio**: BirdNET-Analyzer on Jetson CPU during perch / hover modes only
  (rotor noise dominates at flight speed). 3000+ species via global eBird-derived model.

## Why MegaDetector v6 Compact

- Pre-trained on millions of camera-trap images across the LILA BC corpus.
- Class output: animal / person / vehicle (no species at this stage).
- 30+ FPS on Orin Nano Super, runs concurrently with the fire YOLO head.
- License: MIT (highly permissive; we redistribute weights with attribution).

## Pipeline

```
RGB frame (1 Hz) → MDV6 Compact → bbox + class
  ↓
if class == "animal":
    crop → upload (low-res) to evidence bucket
    species_classifier(crop)  # async, ground-station side
  ↓
emit wildfire_signal(signal_type="wildlife", subtype="megadetector_animal")
```

## Output to Sapphire

Per [`sapphire_integration/wildfire_signal_schema.json`](../../sapphire_integration/wildfire_signal_schema.json),
wildlife signals use:

- `signal_type = "wildlife"`
- `signal_subtype = "wildlife/<class>"` (e.g. `wildlife/animal`, later `wildlife/deer` once species ID is wired)
- `confidence = MDV6 score`
- `risk_score = 0` (wildlife is not a fire signal; risk_score is fire-coded)
- `recommended_action = "log_only"` (never alerts the fire department)

The Sapphire-side router publishes the wildlife subset to the public ecology
API on Cloud Run; fire signals are operational data only.

## Audio (BirdNET)

Activated only when:

```
flight_mode in ["LOITER", "LAND"] and ground_speed_mps < 2.0
```

Captures 3-second windows at 48 kHz mono via SPH0645 I2S MEMS mic. Output:

```json
{"species": "Sturnus vulgaris", "confidence": 0.81, "start_s": 0.0, "end_s": 3.0}
```

These are batched into a single audio-survey signal per perch and emitted as
`signal_type="wildlife"`, `signal_subtype="wildlife/birdnet_audio"`.

## Privacy

If MDV6 returns `class == "person"`:
- We do **not** emit a signal.
- We do **not** retain the frame.
- We do log a counter in flight telemetry for FAA-required incident reporting
  in the rare case a person was detected over an authorized zone (which would
  itself be a flight-plan compliance issue).
