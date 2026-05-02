"""Sanity tests for the curated public-domain image set + labels."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent  # eval/real_bench/

REQUIRED_SECTIONS_IN_IMAGES_README = (
    "Source agency",
    "License",
    "Source URL",
    "17 U.S.C.",
)


def test_images_dir_has_expected_files() -> None:
    images = sorted(p.name for p in (HERE / "images").iterdir() if p.suffix == ".jpg")
    assert len(images) == 12, f"expected 12 images, got {len(images)}: {images}"


def test_images_readme_includes_attribution() -> None:
    text = (HERE / "images" / "README.md").read_text(encoding="utf-8")
    for marker in REQUIRED_SECTIONS_IN_IMAGES_README:
        assert marker in text, f"images/README.md missing required marker: {marker!r}"


def test_labels_yaml_covers_every_image() -> None:
    pytest.importorskip("yaml")
    import yaml  # noqa: PLC0415

    doc = yaml.safe_load((HERE / "labels.yaml").read_text(encoding="utf-8"))
    labeled = {entry["filename"] for entry in doc.get("images") or []}
    on_disk = {p.name for p in (HERE / "images").iterdir() if p.suffix == ".jpg"}
    missing = on_disk - labeled
    extra = labeled - on_disk
    assert not missing, f"images on disk without labels: {missing}"
    assert not extra, f"labels with no on-disk image: {extra}"


def test_labels_have_required_fields() -> None:
    pytest.importorskip("yaml")
    import yaml  # noqa: PLC0415

    doc = yaml.safe_load((HERE / "labels.yaml").read_text(encoding="utf-8"))
    valid_classes = {"fire", "smoke", "thermal_anomaly", "wildlife", "none", "anomaly"}
    for entry in doc.get("images") or []:
        assert "filename" in entry
        assert "expected_class" in entry
        assert entry["expected_class"] in valid_classes, (
            f"{entry['filename']}: unknown class {entry['expected_class']!r}"
        )
        assert "notes" in entry, f"{entry['filename']}: missing notes"


def test_labels_floors_in_range() -> None:
    pytest.importorskip("yaml")
    import yaml  # noqa: PLC0415

    doc = yaml.safe_load((HERE / "labels.yaml").read_text(encoding="utf-8"))
    for entry in doc.get("images") or []:
        floor = entry.get("expected_min_score")
        if floor is None:
            continue
        assert 0.0 <= floor <= 1.0, (
            f"{entry['filename']}: expected_min_score out of [0, 1]: {floor}"
        )


def test_negative_controls_have_null_min_score() -> None:
    """Negative-control labels (none/wildlife) must have null min_score —
    the bench can't expect a confidence floor for something that shouldn't fire.
    """
    pytest.importorskip("yaml")
    import yaml  # noqa: PLC0415

    doc = yaml.safe_load((HERE / "labels.yaml").read_text(encoding="utf-8"))
    for entry in doc.get("images") or []:
        if entry["expected_class"] in {"none", "wildlife"}:
            assert entry.get("expected_min_score") is None, (
                f"{entry['filename']}: negative-control should have "
                f"null expected_min_score, got {entry.get('expected_min_score')}"
            )
