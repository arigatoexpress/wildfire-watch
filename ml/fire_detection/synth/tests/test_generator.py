"""Tests for ml.fire_detection.synth.generator.

Generator tests need PIL + numpy. The CLASS_ID and label-shape sanity checks
do not need PIL and are exercised separately.
"""

from __future__ import annotations

import importlib.util

import pytest

from ml.fire_detection.synth import CLASS_FIRE, CLASS_NAMES, CLASS_SMOKE


HAS_PIL = importlib.util.find_spec("PIL") is not None
HAS_NUMPY = importlib.util.find_spec("numpy") is not None


def test_class_id_constants_are_stable() -> None:
    assert CLASS_FIRE == 0
    assert CLASS_SMOKE == 1
    assert CLASS_NAMES == ["fire", "smoke"]


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_sample_seed_42_returns_image_and_yolo_labels() -> None:
    from ml.fire_detection.synth.generator import generate_sample

    img, labels = generate_sample(
        backdrop=None,
        seed=42,
        has_smoke=True,
        has_fire=True,
        augmentation_level=0.3,
        image_size=(160, 160),
    )

    assert img.size == (160, 160)
    # Labels list should have at least one entry — both classes were requested.
    assert isinstance(labels, list)
    assert all(isinstance(label, dict) for label in labels)

    for label in labels:
        # Required YOLO fields.
        for k in ("class_id", "x_center", "y_center", "width", "height"):
            assert k in label, f"missing field {k} in {label}"
        assert label["class_id"] in (CLASS_FIRE, CLASS_SMOKE)
        # All coords must be normalized to [0, 1].
        for k in ("x_center", "y_center", "width", "height"):
            assert 0.0 <= label[k] <= 1.0, f"{k}={label[k]} not in [0, 1]"
        assert label["width"] > 0.0
        assert label["height"] > 0.0


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_sample_negative_returns_no_labels() -> None:
    from ml.fire_detection.synth.generator import generate_sample

    img, labels = generate_sample(
        backdrop=None,
        seed=7,
        has_smoke=False,
        has_fire=False,
        augmentation_level=0.4,
        image_size=(128, 128),
    )
    assert img.size == (128, 128)
    assert labels == []


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_sample_validates_augmentation_level() -> None:
    from ml.fire_detection.synth.generator import generate_sample

    with pytest.raises(ValueError):
        generate_sample(None, seed=1, has_smoke=True, has_fire=False, augmentation_level=1.5)
    with pytest.raises(ValueError):
        generate_sample(None, seed=1, has_smoke=True, has_fire=False, augmentation_level=-0.1)


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_sample_smoke_only_yields_only_smoke_labels() -> None:
    from ml.fire_detection.synth.generator import generate_sample

    _, labels = generate_sample(
        backdrop=None,
        seed=11,
        has_smoke=True,
        has_fire=False,
        augmentation_level=0.0,
        image_size=(192, 192),
    )
    assert all(label["class_id"] == CLASS_SMOKE for label in labels)


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_sample_fire_only_yields_only_fire_labels() -> None:
    from ml.fire_detection.synth.generator import generate_sample

    _, labels = generate_sample(
        backdrop=None,
        seed=13,
        has_smoke=False,
        has_fire=True,
        augmentation_level=0.0,
        image_size=(192, 192),
    )
    assert all(label["class_id"] == CLASS_FIRE for label in labels)


@pytest.mark.skipif(not (HAS_PIL and HAS_NUMPY), reason="PIL+numpy required")
def test_generate_sample_with_real_backdrop_resizes_to_target() -> None:
    """If a real backdrop is available, the output image must match image_size."""
    from pathlib import Path

    from ml.fire_detection.synth.generator import generate_sample

    repo_root = Path(__file__).resolve().parents[3]
    backdrops_dir = repo_root / "fire_detection" / "eval" / "real_bench" / "images"
    backdrops = sorted(backdrops_dir.glob("*.jpg"))
    if not backdrops:  # pragma: no cover - real_bench is checked in
        pytest.skip("no real_bench backdrops available")
    img, _ = generate_sample(
        backdrop=backdrops[0],
        seed=21,
        has_smoke=True,
        has_fire=False,
        augmentation_level=0.2,
        image_size=(224, 224),
    )
    assert img.size == (224, 224)
