"""Full synthetic dataset generation pipeline.

Produces a YOLO-format dataset directory tree with deterministic seeds:

::

    output_dir/
    +-- data.yaml              # ultralytics-compatible
    +-- images/
    |   +-- train/
    |   +-- val/
    |   +-- test/
    +-- labels/
    |   +-- train/
    |   +-- val/
    |   +-- test/
    +-- manifest.json          # provenance: seed, n_*, backdrop count, generator version

Composition target: 30% fire-only, 30% smoke-only, 20% both, 20% negative.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from . import CLASS_NAMES, GENERATOR_VERSION
from .generator import DEFAULT_H, DEFAULT_W, generate_sample

__all__ = [
    "generate_dataset",
    "DEFAULT_BACKDROPS_DIR",
    "DEFAULT_OUTPUT_DIR",
    "CLASS_BALANCE",
]

# Default backdrop directory: the 12 federal-public-domain images that already
# ship in the repo for the v0.0.1 real-bench eval. License-clean.
DEFAULT_BACKDROPS_DIR = Path("ml/fire_detection/eval/real_bench/images")

# Default output: outside the repo, per CLAUDE.md ("datasets land at
# ~/wildfire-watch-data/<name>/. The directory is not inside the repo.")
DEFAULT_OUTPUT_DIR = Path.home() / "wildfire-watch-data" / "synth-v0"

# Composition mix. Sums to 1.0.
CLASS_BALANCE = {
    "fire_only": 0.30,
    "smoke_only": 0.30,
    "both": 0.20,
    "negative": 0.20,
}

_SUPPORTED_BACKDROP_EXTS = {".jpg", ".jpeg", ".png"}


def _list_backdrops(backdrops_dir: Path) -> list[Path]:
    if not backdrops_dir.exists():
        return []
    return sorted(
        p
        for p in backdrops_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _SUPPORTED_BACKDROP_EXTS
    )


def _label_to_yolo_line(label: dict[str, float]) -> str:
    return (
        f"{int(label['class_id'])} "
        f"{label['x_center']:.6f} "
        f"{label['y_center']:.6f} "
        f"{label['width']:.6f} "
        f"{label['height']:.6f}"
    )


def _split_size_table(n_train: int, n_val: int, n_test: int) -> list[tuple[str, int]]:
    return [("train", n_train), ("val", n_val), ("test", n_test)]


def _balanced_class_flags(n: int, *, seed: int) -> list[tuple[bool, bool]]:
    """Produce a length-n list of (has_fire, has_smoke) flags matching CLASS_BALANCE.

    Deterministic: same n + seed -> identical flags. Counts round to integer
    bucket sizes; any rounding remainder is assigned to the largest bucket
    (fire_only) so the mix never under-represents the dominant class.
    """
    rng = random.Random(seed ^ 0xBA1A11C3)
    counts = {k: int(round(n * v)) for k, v in CLASS_BALANCE.items()}
    drift = n - sum(counts.values())
    if drift != 0:
        # Assign to the largest bucket. Tiebreak alphabetical.
        order = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        counts[order[0][0]] += drift

    flags: list[tuple[bool, bool]] = []
    flags.extend([(True, False)] * counts["fire_only"])
    flags.extend([(False, True)] * counts["smoke_only"])
    flags.extend([(True, True)] * counts["both"])
    flags.extend([(False, False)] * counts["negative"])
    rng.shuffle(flags)
    return flags


def generate_dataset(
    output_dir: Path,
    *,
    n_train: int = 200,
    n_val: int = 50,
    n_test: int = 50,
    seed: int = 42,
    backdrops_dir: Path = DEFAULT_BACKDROPS_DIR,
    image_size: tuple[int, int] = (DEFAULT_W, DEFAULT_H),
    augmentation_level: float = 0.6,
) -> dict[str, Any]:
    """Generate a YOLO-format synthetic dataset on disk.

    Returns
    -------
    The manifest dict that was written to ``<output_dir>/manifest.json``.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    backdrops_dir = Path(backdrops_dir).expanduser()
    if not backdrops_dir.is_absolute():
        # Resolve relative to repo root if running from repo root.
        backdrops_dir = (Path.cwd() / backdrops_dir).resolve()

    backdrops = _list_backdrops(backdrops_dir)

    # Build the directory tree.
    output_dir.mkdir(parents=True, exist_ok=True)
    for subset, _ in _split_size_table(n_train, n_val, n_test):
        (output_dir / "images" / subset).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / subset).mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    per_subset_stats: dict[str, dict[str, int]] = {}
    total_labels = 0

    for subset, count in _split_size_table(n_train, n_val, n_test):
        flags = _balanced_class_flags(count, seed=seed + hash(subset) % 99991)
        rng = random.Random(seed ^ (hash(subset) & 0xFFFFFFFF))
        subset_stats = {
            "samples": 0,
            "fire_labels": 0,
            "smoke_labels": 0,
            "negatives": 0,
        }
        for i, (has_fire, has_smoke) in enumerate(flags):
            sample_seed = (seed * 1_000_003 + hash(subset) + i) & 0xFFFFFFFF
            backdrop_path = (
                backdrops[rng.randrange(len(backdrops))] if backdrops else None
            )
            image, labels = generate_sample(
                backdrop_path,
                seed=sample_seed,
                has_fire=has_fire,
                has_smoke=has_smoke,
                augmentation_level=augmentation_level,
                image_size=image_size,
            )

            stem = f"{subset}_{i:05d}"
            img_path = output_dir / "images" / subset / f"{stem}.jpg"
            lbl_path = output_dir / "labels" / subset / f"{stem}.txt"
            image.save(img_path, "JPEG", quality=88)
            with lbl_path.open("w", encoding="utf-8") as fh:
                for lab in labels:
                    fh.write(_label_to_yolo_line(lab) + "\n")

            subset_stats["samples"] += 1
            for lab in labels:
                if int(lab["class_id"]) == 0:
                    subset_stats["fire_labels"] += 1
                else:
                    subset_stats["smoke_labels"] += 1
            if not labels:
                subset_stats["negatives"] += 1
            total_labels += len(labels)
        per_subset_stats[subset] = subset_stats

    elapsed = time.perf_counter() - t0

    # Write data.yaml.
    data_yaml = output_dir / "data.yaml"
    data_yaml.write_text(
        "# wildfire-watch synthetic dataset (Ultralytics-compatible).\n"
        "# Generated by ml.fire_detection.synth.pipeline; see manifest.json.\n"
        f"path: {output_dir}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names: {list(CLASS_NAMES)}\n",
        encoding="utf-8",
    )

    manifest = {
        "generator": "ml.fire_detection.synth",
        "generator_version": GENERATOR_VERSION,
        "seed": int(seed),
        "image_size": [int(image_size[0]), int(image_size[1])],
        "augmentation_level": float(augmentation_level),
        "n_train": int(n_train),
        "n_val": int(n_val),
        "n_test": int(n_test),
        "n_total": int(n_train + n_val + n_test),
        "class_balance_target": CLASS_BALANCE,
        "class_names": list(CLASS_NAMES),
        "backdrops_dir": str(backdrops_dir),
        "backdrop_count": len(backdrops),
        "backdrop_files": [p.name for p in backdrops],
        "per_subset_stats": per_subset_stats,
        "total_labels": total_labels,
        "elapsed_seconds": round(elapsed, 3),
        "output_dir": str(output_dir),
        "data_yaml": str(data_yaml),
        "license": (
            "Synthetic data is Apache-2.0 (matches the parent repo). Backdrop "
            "imagery is U.S. federal public domain under 17 U.S.C. Sec. 105 — "
            "see ml/fire_detection/eval/real_bench/images/README.md for "
            "per-image attribution."
        ),
        "caveat": (
            "Procedural fire/smoke. Not a substitute for FASDD / FLAME-2 / "
            "D-Fire (see DATASETS.md). Models trained only on this set will "
            "overfit to Perlin-noise statistics; eval against real_bench/ "
            "before any release claim."
        ),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return manifest
