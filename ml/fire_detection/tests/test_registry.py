"""Tests for ml/fire_detection/registry.py.

Strategy: hit the real on-disk runs/ directory (so we exercise v0.0.1 as
shipped), plus a tmp-dir test for edge cases (malformed manifest, missing
eval, version sort order).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from ml.fire_detection.registry import (  # noqa: E402
    ModelEntry,
    _parse_version_tuple,
    get,
    list_models,
    shipped_count,
)

V0_0_1 = "wfw-fire-heuristic-v0.0.1"


def test_list_models_finds_v0_0_1() -> None:
    """The shipped v0.0.1 baseline is on disk and discoverable."""
    entries = list_models()
    assert len(entries) >= 1
    ids = [e.model_id for e in entries]
    assert V0_0_1 in ids


def test_get_by_model_id() -> None:
    e = get(V0_0_1)
    assert e is not None
    assert isinstance(e, ModelEntry)
    assert e.model_id == V0_0_1
    assert e.version == "0.0.1"


def test_get_by_version_string() -> None:
    a = get("0.0.1")
    b = get("v0.0.1")
    assert a is not None
    assert b is not None
    assert a.model_id == V0_0_1
    assert b.model_id == V0_0_1
    # Same underlying entry.
    assert a.path == b.path


def test_get_by_model_id_and_version_match_same_entry() -> None:
    a = get(V0_0_1)
    b = get("0.0.1")
    assert a is not None and b is not None
    assert a.path == b.path
    assert a.released_at == b.released_at


def test_get_latest_returns_highest_version() -> None:
    e = get("latest")
    assert e is not None
    # v0.0.1 is the highest version today; make sure 'latest' resolves to
    # something plausible (highest by semver tuple).
    entries = list_models()
    assert e.version == entries[-1].version


def test_get_unknown_returns_none() -> None:
    assert get("not-a-real-model-zzz") is None
    assert get("9.9.9") is None
    assert get("") is None


def test_shipped_count_matches_list_models() -> None:
    assert shipped_count() == len(list_models())
    assert shipped_count() >= 1


def test_manifest_required_fields_for_every_entry() -> None:
    """Every entry's manifest must carry the core provenance fields.

    These are the fields downstream tooling (KPIs, dashboards, model-card
    generators) is going to grep. Missing any one breaks them silently.
    """
    required = {"model_id", "version", "type", "license", "code_sha", "released_at"}
    for e in list_models():
        missing = required - set(e.manifest.keys())
        assert not missing, f"{e.model_id} manifest missing fields: {missing}"


def test_v0_0_1_eval_has_synthetic_metrics() -> None:
    e = get("0.0.1")
    assert e is not None
    metrics = e.eval.get("metrics") or {}
    # At least precision + recall numbers must be present (synthetic eval).
    assert "precision" in metrics
    assert "recall" in metrics
    # Numeric and finite.
    assert isinstance(metrics["precision"], (int, float))
    assert isinstance(metrics["recall"], (int, float))
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0


def test_v0_0_1_path_exists_and_has_inference_script() -> None:
    e = get("0.0.1")
    assert e is not None
    assert e.path.is_dir()
    assert (e.path / "inference.py").exists()


# ---------------------------------------------------------------------------
# tmp-dir tests for edge cases.
# ---------------------------------------------------------------------------


def _write(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def test_invalid_version_dirs_are_skipped(tmp_path: Path) -> None:
    """Directory names that don't match v\\d+\\.\\d+\\.\\d+ are ignored."""
    runs = tmp_path / "runs"
    runs.mkdir()
    # Valid:
    _write(
        runs / "v1.2.3" / "manifest.json",
        {
            "model_id": "x",
            "version": "1.2.3",
            "type": "deterministic-heuristic",
            "license": "Apache-2.0",
            "code_sha": "abc",
            "released_at": "2026-01-01T00:00:00Z",
        },
    )
    _write(runs / "v1.2.3" / "eval.json", {"metrics": {"precision": 1.0, "recall": 1.0}})
    # Invalid (random folder, no manifest):
    (runs / "scratch").mkdir()
    (runs / "scratch" / "notes.txt").write_text("hello", encoding="utf-8")
    # Invalid (looks like a version but missing eval):
    _write(
        runs / "v0.5.0" / "manifest.json",
        {
            "model_id": "y",
            "version": "0.5.0",
            "type": "x",
            "license": "x",
            "code_sha": "x",
            "released_at": "x",
        },
    )

    entries = list_models(runs_dir=runs)
    assert [e.version for e in entries] == ["1.2.3"]


def test_version_sort_order(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    for v in ("v0.0.1", "v0.10.0", "v0.2.0", "v1.0.0"):
        _write(
            runs / v / "manifest.json",
            {
                "model_id": v,
                "version": v.lstrip("v"),
                "type": "x",
                "license": "x",
                "code_sha": "x",
                "released_at": "x",
            },
        )
        _write(runs / v / "eval.json", {"metrics": {"precision": 1.0, "recall": 1.0}})
    entries = list_models(runs_dir=runs)
    versions = [e.version for e in entries]
    assert versions == ["0.0.1", "0.2.0", "0.10.0", "1.0.0"]
    # 'latest' resolves to the top.
    assert get("latest", runs_dir=runs).version == "1.0.0"  # type: ignore[union-attr]


def test_parse_version_tuple_basic() -> None:
    assert _parse_version_tuple("0.0.1") == (0, 0, 1)
    assert _parse_version_tuple("v0.10.0") == (0, 10, 0)
    assert _parse_version_tuple("1.2.3-rc1") == (1, 2, 3)
    assert _parse_version_tuple("2") == (2, 0, 0)


def test_malformed_manifest_returns_none(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    (runs / "v1.0.0").mkdir(parents=True)
    (runs / "v1.0.0" / "manifest.json").write_text("not json", encoding="utf-8")
    (runs / "v1.0.0" / "eval.json").write_text("{}", encoding="utf-8")
    assert list_models(runs_dir=runs) == []


def test_shipped_count_with_empty_runs(tmp_path: Path) -> None:
    runs = tmp_path / "empty_runs"
    runs.mkdir()
    assert shipped_count(runs_dir=runs) == 0
