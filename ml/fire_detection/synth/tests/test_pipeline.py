"""Tests for ml.fire_detection.synth.pipeline.

Pipeline tests are fully PIL+numpy gated — when those wheels aren't present
the pipeline can't write JPEGs. The split-balancing helper is pure stdlib and
does not need either.
"""

from __future__ import annotations

import importlib.util
import json

import pytest

from ml.fire_detection.synth.pipeline import (
    CLASS_BALANCE,
    _balanced_class_flags,
)


HAS_PIL = importlib.util.find_spec("PIL") is not None
HAS_NUMPY = importlib.util.find_spec("numpy") is not None


def test_class_balance_sums_to_one() -> None:
    assert pytest.approx(sum(CLASS_BALANCE.values())) == 1.0


def test_balanced_class_flags_length_matches_n() -> None:
    flags = _balanced_class_flags(20, seed=42)
    assert len(flags) == 20


def test_balanced_class_flags_deterministic() -> None:
    a = _balanced_class_flags(50, seed=7)
    b = _balanced_class_flags(50, seed=7)
    assert a == b


def test_balanced_class_flags_distribution_close_to_target() -> None:
    flags = _balanced_class_flags(100, seed=42)
    counts = {
        "fire_only": sum(1 for f, s in flags if f and not s),
        "smoke_only": sum(1 for f, s in flags if s and not f),
        "both": sum(1 for f, s in flags if f and s),
        "negative": sum(1 for f, s in flags if not f and not s),
    }
    assert counts["fire_only"] + counts["smoke_only"] + counts["both"] + counts["negative"] == 100
    # Allow +/-2 from the rounded target since rounding-drift may shift one.
    for k, target_frac in CLASS_BALANCE.items():
        assert abs(counts[k] - 100 * target_frac) <= 2


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_dataset_smoke(tmp_path) -> None:
    from ml.fire_detection.synth.pipeline import generate_dataset

    out = tmp_path / "ds"
    manifest = generate_dataset(
        out,
        n_train=4,
        n_val=2,
        n_test=2,
        seed=42,
        image_size=(96, 96),
        augmentation_level=0.2,
    )
    assert manifest["n_total"] == 8

    # Directory tree.
    assert (out / "data.yaml").is_file()
    assert (out / "manifest.json").is_file()
    for subset in ("train", "val", "test"):
        assert (out / "images" / subset).is_dir()
        assert (out / "labels" / subset).is_dir()

    # Image counts per split.
    assert len(list((out / "images" / "train").glob("*.jpg"))) == 4
    assert len(list((out / "images" / "val").glob("*.jpg"))) == 2
    assert len(list((out / "images" / "test").glob("*.jpg"))) == 2

    # Each image has a sibling label file (possibly empty for negatives).
    for img_path in (out / "images" / "train").glob("*.jpg"):
        lbl = out / "labels" / "train" / (img_path.stem + ".txt")
        assert lbl.is_file()

    # Manifest shape.
    on_disk = json.loads((out / "manifest.json").read_text())
    assert on_disk["seed"] == 42
    assert on_disk["n_train"] == 4
    assert on_disk["n_val"] == 2
    assert on_disk["n_test"] == 2
    assert on_disk["n_total"] == 8
    assert on_disk["class_names"] == ["fire", "smoke"]
    assert "generator_version" in on_disk
    assert "per_subset_stats" in on_disk
    assert set(on_disk["per_subset_stats"].keys()) == {"train", "val", "test"}

    # data.yaml is well-formed text.
    yaml_text = (out / "data.yaml").read_text()
    assert "nc: 2" in yaml_text
    assert "names:" in yaml_text
    assert "train:" in yaml_text
    assert "val:" in yaml_text
    assert "test:" in yaml_text


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_dataset_label_lines_are_valid_yolo(tmp_path) -> None:
    from ml.fire_detection.synth.pipeline import generate_dataset

    out = tmp_path / "ds"
    generate_dataset(
        out,
        n_train=4,
        n_val=2,
        n_test=2,
        seed=42,
        image_size=(96, 96),
        augmentation_level=0.0,
    )
    for label_file in (out / "labels").rglob("*.txt"):
        for line in label_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            assert len(parts) == 5
            cls = int(parts[0])
            assert cls in (0, 1)
            cx, cy, w, h = (float(p) for p in parts[1:])
            assert 0.0 <= cx <= 1.0
            assert 0.0 <= cy <= 1.0
            assert 0.0 < w <= 1.0
            assert 0.0 < h <= 1.0


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_dataset_is_seed_reproducible(tmp_path) -> None:
    from ml.fire_detection.synth.pipeline import generate_dataset

    a = generate_dataset(tmp_path / "a", n_train=2, n_val=1, n_test=1, seed=99, image_size=(96, 96))
    b = generate_dataset(tmp_path / "b", n_train=2, n_val=1, n_test=1, seed=99, image_size=(96, 96))
    # Seed-determined fields should match.
    assert a["seed"] == b["seed"]
    assert a["n_total"] == b["n_total"]
    assert a["per_subset_stats"]["train"]["fire_labels"] == b["per_subset_stats"]["train"]["fire_labels"]
    assert a["per_subset_stats"]["train"]["smoke_labels"] == b["per_subset_stats"]["train"]["smoke_labels"]
