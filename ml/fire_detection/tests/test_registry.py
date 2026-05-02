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
    ALLOWED_STATUSES,
    STATUS_RELEASED,
    STATUS_TRAINING_READY,
    STATUS_UNKNOWN,
    ModelEntry,
    _parse_version_tuple,
    count_by_status,
    get,
    list_models,
    shipped_count,
)

V0_0_1 = "wfw-fire-heuristic-v0.0.1"
V0_1_0 = "wfw-fire-yolov8n-v0.1.0"


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


# ---------------------------------------------------------------------------
# v0.1.0 + status-field tests (added with the v0.1.0 ship).
# ---------------------------------------------------------------------------


def test_v0_1_0_in_registry() -> None:
    """The shipped v0.1.0 YOLOv8n recipe is on disk and discoverable."""
    entries = list_models()
    assert len(entries) >= 2
    ids = [e.model_id for e in entries]
    assert V0_1_0 in ids


def test_v0_1_0_shipped_count() -> None:
    """Both v0.0.1 and v0.1.0 count as shipped (RELEASED + TRAINING_READY)."""
    assert shipped_count() >= 2


def test_v0_1_0_manifest_status() -> None:
    """v0.1.0's manifest has a `status` field with a value in the closed set."""
    e = get(V0_1_0)
    assert e is not None
    assert e.manifest.get("status") is not None
    raw = str(e.manifest["status"]).upper()
    assert raw in {"RELEASED", "TRAINING_READY", "BLOCKED"}, (
        f"unexpected status {raw!r}"
    )
    assert e.status == raw


def test_v0_0_1_status_is_released() -> None:
    """v0.0.1 was retroactively given status=RELEASED for consistency."""
    e = get(V0_0_1)
    assert e is not None
    assert e.status == STATUS_RELEASED


def test_v0_1_0_status_is_training_ready() -> None:
    """v0.1.0 ships as TRAINING_READY (recipe + manifest + entrypoint, weights pending)."""
    e = get(V0_1_0)
    assert e is not None
    assert e.status == STATUS_TRAINING_READY


def test_status_field_normalized_lowercase(tmp_path: Path) -> None:
    """Lowercase or mixed-case status values are normalized to upper."""
    runs = tmp_path / "runs"
    _write(
        runs / "v3.0.0" / "manifest.json",
        {
            "model_id": "lowercase-status",
            "version": "3.0.0",
            "status": "training_ready",
            "type": "x",
            "license": "x",
            "code_sha": "x",
            "released_at": "x",
        },
    )
    _write(runs / "v3.0.0" / "eval.json", {"metrics": {"precision": 1.0, "recall": 1.0}})
    entry = get("3.0.0", runs_dir=runs)
    assert entry is not None
    assert entry.status == STATUS_TRAINING_READY


def test_status_field_unknown_value_falls_back(tmp_path: Path) -> None:
    """Manifests carrying a status value outside the allowed set normalize to UNKNOWN."""
    runs = tmp_path / "runs"
    _write(
        runs / "v4.0.0" / "manifest.json",
        {
            "model_id": "weird-status",
            "version": "4.0.0",
            "status": "WIP",
            "type": "x",
            "license": "x",
            "code_sha": "x",
            "released_at": "x",
        },
    )
    _write(runs / "v4.0.0" / "eval.json", {"metrics": {"precision": 1.0, "recall": 1.0}})
    entry = get("4.0.0", runs_dir=runs)
    assert entry is not None
    assert entry.status == STATUS_UNKNOWN


def test_status_field_missing_defaults_unknown(tmp_path: Path) -> None:
    """Pre-status-convention manifests don't crash; they default to UNKNOWN."""
    runs = tmp_path / "runs"
    _write(
        runs / "v5.0.0" / "manifest.json",
        {
            "model_id": "no-status",
            "version": "5.0.0",
            "type": "x",
            "license": "x",
            "code_sha": "x",
            "released_at": "x",
        },
    )
    _write(runs / "v5.0.0" / "eval.json", {"metrics": {"precision": 1.0, "recall": 1.0}})
    entry = get("5.0.0", runs_dir=runs)
    assert entry is not None
    assert entry.status == STATUS_UNKNOWN


def test_count_by_status_returns_full_buckets() -> None:
    """count_by_status returns a dict over all allowed statuses (some may be 0)."""
    counts = count_by_status()
    for s in ALLOWED_STATUSES:
        assert s in counts
    # On the live shipped registry, we expect at least 1 RELEASED + 1 TRAINING_READY.
    assert counts[STATUS_RELEASED] >= 1
    assert counts[STATUS_TRAINING_READY] >= 1


def test_to_dict_includes_status() -> None:
    """ModelEntry.to_dict() exposes the new status field for serialization."""
    e = get(V0_1_0)
    assert e is not None
    d = e.to_dict()
    assert "status" in d
    assert d["status"] == STATUS_TRAINING_READY


def test_v0_1_0_eval_is_explicitly_not_yet_trained() -> None:
    """v0.1.0's eval.json explicitly carries the not_yet_trained sentinel.

    Critical: the dispatch scope says NO fake metrics. v0.1.0's eval JSON
    must explicitly say it isn't trained, not pretend to have measured
    numbers.
    """
    e = get(V0_1_0)
    assert e is not None
    assert e.eval.get("status") == "not_yet_trained"
    # Either metrics is None, or it's a dict but with no top-line target hit.
    metrics = e.eval.get("metrics")
    assert metrics is None or metrics == {}


# ---------------------------------------------------------------------------
# Archetype-flip test (verifies the valuation-engine integration).
# ---------------------------------------------------------------------------


def test_archetype_flip_triggered_by_v0_1_0() -> None:
    """With models>=2 + signals>=100, _pick_archetype returns computer-vision-defense.

    This is the load-bearing assertion of the v0.1.0 ship: the registered
    second model trips the gate in valuation/methods.py::_pick_archetype,
    which flips the comparable_multiples archetype from drone-in-a-box to
    computer-vision-defense (Shield AI multiples).
    """
    from valuation.methods import _pick_archetype  # noqa: PLC0415

    snapshot = {
        "model_versions_shipped": 2,
        "signals_emitted_total": 200,
        "partner_agencies_engaged": 0,
        "letters_of_authorization_count": 0,
        "simulator_runs_total": 0,
        "mission_zones_count": 0,
        "ndaa_blue_uas_eligible": False,
    }
    assert _pick_archetype(snapshot) == "computer-vision-defense"


def test_archetype_no_flip_with_signals_below_threshold() -> None:
    """If signals < 100, the archetype gate doesn't trip even with 2 models."""
    from valuation.methods import _pick_archetype  # noqa: PLC0415

    snapshot = {
        "model_versions_shipped": 2,
        "signals_emitted_total": 50,
        "partner_agencies_engaged": 0,
        "letters_of_authorization_count": 0,
        "simulator_runs_total": 0,
        "mission_zones_count": 0,
        "ndaa_blue_uas_eligible": False,
    }
    # With models=2 but signals<100, fall through to defense-tech-platform default
    # (sim_runs+zones gate also misses, ndaa is False).
    assert _pick_archetype(snapshot) == "defense-tech-platform"


def test_archetype_flip_takes_priority_over_drone_in_a_box() -> None:
    """When both gates are satisfied, computer-vision-defense wins (it's checked first)."""
    from valuation.methods import _pick_archetype  # noqa: PLC0415

    snapshot = {
        "model_versions_shipped": 2,
        "signals_emitted_total": 5000,
        "partner_agencies_engaged": 0,
        "letters_of_authorization_count": 0,
        "simulator_runs_total": 100,   # would trigger drone-in-a-box
        "mission_zones_count": 5,      # would trigger drone-in-a-box
        "ndaa_blue_uas_eligible": False,
    }
    assert _pick_archetype(snapshot) == "computer-vision-defense"
