"""Tests for eval/targets.yaml and prep_datasets.py loading.

These tests must pass without pyyaml installed (prep_datasets ships a
stdlib fallback parser for the narrow YAML shape we use). They also pass with
pyyaml installed.

Schema rules enforced here:
  - schema_version is "1.0.0"
  - detection.primary_metric is the canonical name we paste into MODEL_CARD.md
  - latency.jetson_orin_super_fp16_p95_ms is a positive number
  - every dataset entry has the required keys
  - no dataset has a real-looking SHA256 yet (we want TBDs until first download)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from ml.fire_detection.eval.prep_datasets import (  # noqa: E402
    DatasetSpec,
    _parse_targets_fallback,
    load_specs,
)

TARGETS_PATH = Path(__file__).resolve().parents[1] / "targets.yaml"


def test_targets_yaml_exists_and_nonempty() -> None:
    assert TARGETS_PATH.exists()
    assert TARGETS_PATH.stat().st_size > 0


def test_load_specs_returns_three_datasets() -> None:
    specs = load_specs(TARGETS_PATH)
    assert set(specs.keys()) == {"fasdd", "flame2", "dfire"}


def test_each_spec_has_required_fields() -> None:
    specs = load_specs(TARGETS_PATH)
    for name, spec in specs.items():
        assert isinstance(spec, DatasetSpec), name
        assert spec.name == name
        assert spec.role in {"pretrain", "finetune", "holdout_eval"}, name
        assert spec.license, name
        assert spec.download_url.startswith("http"), name
        assert spec.homepage_url.startswith("http"), name
        assert spec.expected_image_count_min > 0, name
        assert spec.expected_image_count_max >= spec.expected_image_count_min, name


def test_dfire_is_holdout_eval() -> None:
    specs = load_specs(TARGETS_PATH)
    assert specs["dfire"].role == "holdout_eval"
    # D-Fire is CC-BY-NC. If this changes upstream, MODEL_CARD.md needs an update.
    assert specs["dfire"].license == "CC-BY-NC-4.0"


def test_fasdd_and_flame2_are_pretrain_and_finetune() -> None:
    specs = load_specs(TARGETS_PATH)
    assert specs["fasdd"].role == "pretrain"
    assert specs["flame2"].role == "finetune"


def test_no_dataset_has_real_sha256_yet() -> None:
    """The TBD pattern is intentional — we do not commit fabricated hashes.

    If this test starts failing because someone added a real digest, that's
    fine — just delete this test in the same commit and update DATASETS.md.
    """
    specs = load_specs(TARGETS_PATH)
    for name, spec in specs.items():
        assert spec.sha256.startswith("TBD"), (
            f"{name}: sha256 is no longer TBD ({spec.sha256!r}). "
            "Update DATASETS.md and remove this guard."
        )


def test_fallback_parser_matches_shape_of_pyyaml() -> None:
    text = TARGETS_PATH.read_text()
    parsed = _parse_targets_fallback(text)
    assert "datasets" in parsed
    for name in ("fasdd", "flame2", "dfire"):
        assert name in parsed["datasets"], name
        ds = parsed["datasets"][name]
        assert "license" in ds
        assert "download_url" in ds
        assert "requires_manual_download" in ds
        assert ds["requires_manual_download"] is True


def test_schema_version_is_v1() -> None:
    """Schema_version is part of our forward-compat contract — pin it."""
    text = TARGETS_PATH.read_text()
    assert 'schema_version: "1.0.0"' in text or "schema_version: '1.0.0'" in text


def test_detection_section_has_primary_metric() -> None:
    text = TARGETS_PATH.read_text()
    assert "primary_metric: precision_at_recall_0.80" in text
    assert "primary_target: 0.95" in text


def test_jetson_p95_target_is_25ms() -> None:
    text = TARGETS_PATH.read_text()
    assert "jetson_orin_super_fp16_p95_ms: 25" in text


@pytest.mark.parametrize("name", ["fasdd", "flame2", "dfire"])
def test_dataset_paper_url_present(name: str) -> None:
    """We refuse to ship a dataset reference without a paper link."""
    specs = load_specs(TARGETS_PATH)
    assert specs[name].paper_url.startswith("http"), name
