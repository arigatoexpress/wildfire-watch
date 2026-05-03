"""Synthetic-data training pipeline for the wildfire-watch fire/smoke detector.

This package produces a YOLO-format training dataset entirely from procedural
generators + 12 federal-public-domain backdrops already shipped in
`ml/fire_detection/eval/real_bench/images/`. It does NOT depend on the
auth-walled FASDD / FLAME-2 / D-Fire archives — those remain the v0.1.0 RELEASED
training-data plan; this package is the v0.1.0 TRAINING_READY interim claim.

The synthesizers are deterministic given a seed. Every PIL / numpy import is
lazy so the test suite imports cleanly in an environment without those wheels;
only the pieces that actually compose pixels demand them.

Modules
-------
- ``procedural``: Perlin-noise-driven smoke plumes, radial fire glow, and false
  -colour thermal anomaly patches.
- ``augmentation``: brightness, colour-temperature, Gaussian noise, perspective
  warp, and canopy-occlusion augmentations.
- ``generator``: composes a single (image, YOLO-labels) pair from a backdrop +
  procedural overlays.
- ``pipeline``: produces a full `images/` + `labels/` + `data.yaml` directory
  tree across train / val / test splits.
- ``cli``: ``python -m ml.fire_detection.synth.cli`` entry-point.
"""

from __future__ import annotations

__all__ = [
    "GENERATOR_VERSION",
    "CLASS_FIRE",
    "CLASS_SMOKE",
    "CLASS_NAMES",
]

# Bumping this fingerprint forces a re-generation of any downstream artefact
# manifests that pin to the generator version. Bump on any visible change to
# the procedural composition or label semantics.
GENERATOR_VERSION = "0.1.0"

CLASS_FIRE = 0
CLASS_SMOKE = 1
CLASS_NAMES = ["fire", "smoke"]
