# ADR-0001: Edge compute platform — Jetson Orin Nano Super

**Status**: Accepted, 2026-05-01
**Decider**: Operator
**Context**: Choosing the on-drone compute board for fire + wildlife inference.

## Decision

Adopt **NVIDIA Jetson Orin Nano Super 8 GB Developer Kit** as the standard
edge-compute board for all wildfire-watch units, MVP and beyond.

## Options considered

| Option | TOPS | Power | Price | Weight | ML stack |
|---|---:|---:|---:|---:|---|
| Jetson Orin Nano Super 8 GB | 67 | 7-25 W | $249 | ~70 g (board) | Full CUDA + TensorRT |
| Raspberry Pi 5 8 GB + Hailo-8L M.2 | 13 | ~6 W | ~$155 ($75 + $70 + carrier) | ~75 g | HailoRT compiler |
| Raspberry Pi 5 + Hailo-8 (full) | 26 | ~9 W | ~$235 | ~80 g | HailoRT compiler |
| Coral Dev Board Mini | 4 (TPU only) | 2.5 W | $99 | ~30 g | TFLite only |
| OAK-D Lite (Movidius Myriad X) | 4 | 4 W | $149 | 75 g | OpenVINO/DepthAI |

## Trade-off summary

**Power**: Pi 5 + Hailo-8L wins on power (5-6 W vs. 15-25 W). With our 8000 mAh
4S Li-Ion (~118 Wh), the compute-power delta is ~10 W × 0.5 h = 5 Wh, ~4% of
total battery. Not negligible, but flight-controller + motors dominate by
50× — the compute power difference moves endurance by ~1-2 minutes, not
materially.

**TOPS**: Orin Nano Super at 67 TOPS is 5× the Hailo-8L's 13 TOPS. Real-world
benchmark: ~157 FPS YOLOv8n vs. ~77 FPS on Pi 5 + Hailo-8. We need headroom for
fire YOLO + MegaDetector v6 + anomaly head running concurrently — Hailo-8L
forces us to multiplex/serialize.

**Software**: Orin Nano runs **anything** that compiles for CUDA — PyTorch,
ONNX, TensorRT, all the ecology models, BirdNET, hand-rolled CUDA kernels for
thermal-image processing. Hailo-8L requires HailoRT compilation per model;
many of our models don't compile cleanly to Hailo's ops (especially the dynamic
shapes in MegaDetector v6's YOLOv10 head).

**Cost**: Orin Nano Super at $249 is the cheapest TOPS-per-dollar in the
comparison table — NVIDIA 2025-Q4 price cut made this the no-brainer. Pi 5 +
Hailo-8L total comes in under $200 only after carrier-board hunting.

**Weight**: Effectively a tie (~70-80 g for any of them). Doesn't drive the
decision.

**Heat**: Orin Nano runs hotter — needs active cooling (25 mm fan in our pod
design). Pi 5 + Hailo-8L is passive-cooled-friendly. We accept the active fan
as a known maintenance item.

## Decision

**Jetson Orin Nano Super 8 GB**, because:

1. ML headroom for the 3-head ensemble (fire + wildlife + anomaly) without
   model multiplexing.
2. CUDA ecosystem flexibility — we can ship novel models without waiting on
   the HailoRT compiler matching new ops.
3. $249 price point is below Pi 5 + Hailo-8 (full) and within $100 of Pi 5 +
   Hailo-8L, with materially more compute.
4. NVIDIA's edge-AI roadmap is well-documented; Hailo's is less so.

## Consequences

- We pay ~$100/unit more than the cheapest viable alternative. Acceptable at
  MVP scale (2 units = $200 more). Will revisit at Phase-3 if we scale to 50+ units.
- We carry the Orin Nano's higher idle power. Endurance budget assumes this.
- We need active cooling on every unit (25 mm fan in pod design); fan
  reliability is a known maintenance item.
- We commit to the CUDA ecosystem; can't easily port to a low-power Hailo
  variant later without rewriting model exports.

## When to reconsider

- If NVIDIA EOLs Orin Nano (no signal as of 2026-Q1).
- If a 50-TOPS + 5W board appears (Hailo-10 rumored, not shipping).
- If a fleet operator's power-per-flight calculus dominates compute headroom
  (e.g. 60+ minute endurance target where every watt matters).
