"""Real-image evaluation bench for the wfw-fire-heuristic-v0.0.1 baseline.

This package runs the v0.0.1 colour-temperature heuristic against a small,
curated set of public-domain wildfire/smoke imagery and writes a Markdown
report. It is the qualitative bridge between v0.0.1's synthetic eval (in
the parent ``eval/`` directory, scored on the (rgb_score, thermal_delta_c)
plane) and v0.1.0's planned D-Fire holdout eval.

The bench is intentionally small (6-12 images) and fully reproducible:
every image is downloaded from a federal-government public-domain source,
attribution lives in ``images/README.md``, and ground-truth labels live in
``labels.yaml``.
"""

__all__ = ["bench"]
