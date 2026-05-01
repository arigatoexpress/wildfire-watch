"""Unit tests for the on-drone fusion gate + signal builder.

Exercises pure logic only — no camera, no MAVLink, no network. These are
the safety-critical parts of the inference loop where a bug could either
mask a real fire (false negative) or trigger a needless fire-dept page
(false positive).

Run:
    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/test_infer.py -q
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from infer import SCHEMA_VERSION, build_signal, should_emit  # noqa: E402


# ---------------------------------------------------------------------------
# should_emit — the multimodal fusion gate. Defaults match docs/30-ml-stack.md.
# ---------------------------------------------------------------------------


@pytest.fixture
def baseline_kwargs() -> dict[str, float | bool | int]:
    return {
        "rgb_score": 0.90,
        "thermal_delta_c": 12.0,
        "persistence_frames": 5,
        "geofence_ok": True,
        "wind_consistent": True,
        "threshold": 0.65,
        "persistence_min": 5,
    }


def test_should_emit_baseline_passes(baseline_kwargs: dict) -> None:
    assert should_emit(**baseline_kwargs) is True


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"rgb_score": 0.50}, "below RGB threshold"),
        ({"thermal_delta_c": 2.0}, "thermal delta too low"),
        ({"persistence_frames": 3}, "persistence not yet met"),
        ({"geofence_ok": False}, "outside authorized zone"),
        ({"wind_consistent": False}, "wind direction sanity check failed"),
    ],
)
def test_should_emit_blocks_each_failure_mode(
    baseline_kwargs: dict, override: dict, reason: str
) -> None:
    kwargs = {**baseline_kwargs, **override}
    assert should_emit(**kwargs) is False, reason


def test_should_emit_thermal_delta_floor_is_5c(baseline_kwargs: dict) -> None:
    """Thermal delta floor is 5 C — below that, RGB-only is not enough.

    This locks the design choice: fire detection requires BOTH a positive
    RGB classification AND a positive thermal anomaly. The 5 C threshold is
    documented in docs/30-ml-stack.md.
    """
    just_below = {**baseline_kwargs, "thermal_delta_c": 4.99}
    just_above = {**baseline_kwargs, "thermal_delta_c": 5.0}
    assert should_emit(**just_below) is False
    assert should_emit(**just_above) is True


def test_should_emit_persistence_floor(baseline_kwargs: dict) -> None:
    """Edge: persistence_frames must be >= persistence_min, not strictly greater."""
    kwargs = {**baseline_kwargs, "persistence_frames": 5, "persistence_min": 5}
    assert should_emit(**kwargs) is True
    kwargs = {**baseline_kwargs, "persistence_frames": 4, "persistence_min": 5}
    assert should_emit(**kwargs) is False


# ---------------------------------------------------------------------------
# build_signal — schema conformance. Bugs here put garbage into Sapphire.
# ---------------------------------------------------------------------------


def _signal(**overrides) -> dict:
    base = {
        "drone_id": "wfw-unit01",
        "zone_id": "test-zone",
        "coords": {"lat": 36.5, "lon": -121.2, "alt_agl_m": 80.0},
        "target_coords": None,
        "signal_type": "smoke",
        "confidence": 0.91,
        "rgb_yolo_score": 0.93,
        "thermal_delta_c": 18.5,
        "frame_uris": ["gs://wildfire-watch-evidence/test/frame_01.jpg"],
        "risk_score": 78.0,
        "recommended_action": "notify_operator",
    }
    base.update(overrides)
    return build_signal(**base)


def test_build_signal_shape_matches_schema_v1() -> None:
    sig = _signal()
    required = {
        "schema_version",
        "signal_id",
        "drone_id",
        "zone_id",
        "timestamp",
        "coords",
        "signal_type",
        "confidence",
        "evidence",
        "risk_score",
        "recommended_action",
    }
    assert required.issubset(sig.keys())
    assert sig["schema_version"] == SCHEMA_VERSION


def test_build_signal_signal_id_is_uuid4() -> None:
    sig = _signal()
    parsed = uuid.UUID(sig["signal_id"])
    assert parsed.version == 4


def test_build_signal_timestamp_iso_zulu() -> None:
    sig = _signal()
    ts = sig["timestamp"]
    assert ts.endswith("Z"), "drone-side timestamps should be Zulu-suffixed"
    assert "T" in ts


def test_build_signal_evidence_includes_model_outputs() -> None:
    sig = _signal()
    outputs = sig["evidence"]["model_outputs"]
    assert outputs["rgb_yolo_score"] == 0.93
    assert outputs["thermal_delta_c"] == 18.5
    assert sig["evidence"]["frame_uris"] == [
        "gs://wildfire-watch-evidence/test/frame_01.jpg"
    ]


def test_build_signal_geofence_status_compliant_by_default() -> None:
    sig = _signal()
    gf = sig["geofence_status"]
    assert gf["in_authorized_zone"] is True
    assert gf["tfr_active"] is False
    assert gf["remote_id_active"] is True


def test_build_signal_serializes_to_json() -> None:
    """The schema_info contract is JSONL-appendable, so the dict must round-trip."""
    sig = _signal()
    text = json.dumps(sig)
    parsed = json.loads(text)
    assert parsed["signal_id"] == sig["signal_id"]


def test_build_signal_two_calls_produce_distinct_ids() -> None:
    a = _signal()
    b = _signal()
    assert a["signal_id"] != b["signal_id"], "every emit must have a fresh UUID"
