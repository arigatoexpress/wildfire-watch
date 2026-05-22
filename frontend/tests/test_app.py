"""Smoke tests for the wildfire-watch admin frontend Flask app."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from frontend.app import (
    compute_kpis,
    compute_sensor_health,
    create_app,
    filter_signals,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sig(
    *,
    drone="wfw-unit01",
    zone="slate-river-drainage",
    signal_type="smoke",
    risk=60.0,
    confidence=0.7,
    minutes_ago=30,
    lat=38.91,
    lon=-107.0,
):
    ts = (
        datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    ).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0.0",
        "signal_id": str(uuid.uuid4()),
        "drone_id": drone,
        "zone_id": zone,
        "timestamp": ts,
        "coords": {"lat": lat, "lon": lon, "alt_agl_m": 80.0},
        "signal_type": signal_type,
        "confidence": confidence,
        "evidence": {"frame_uris": ["file://x.jpg"]},
        "risk_score": risk,
        "recommended_action": "log_only",
    }


@pytest.fixture
def signals_jsonl(tmp_path: Path) -> Path:
    rows = [
        _sig(signal_type="smoke", risk=80.0, minutes_ago=10),
        _sig(signal_type="fire", risk=95.0, minutes_ago=120, zone="cement-creek-drainage"),
        _sig(signal_type="system_event", risk=0.0, minutes_ago=2, drone="wfw-rari1"),
        _sig(signal_type="wildlife", risk=10.0, minutes_ago=60 * 24 * 8),  # > 7d
    ]
    path = tmp_path / "wildfire_signals.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def app_no_auth(signals_jsonl: Path, monkeypatch, tmp_path):
    os.environ.pop("ADMIN_TOKEN", None)
    monkeypatch.setenv("SENSOR_HEALTH_POLL_DISABLED", "1")
    app = create_app(
        signals_path=signals_jsonl,
        sensor_state_path=tmp_path / "sensor_state.json",
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app_with_auth(signals_jsonl: Path, monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("SENSOR_HEALTH_POLL_DISABLED", "1")
    app = create_app(
        signals_path=signals_jsonl,
        sensor_state_path=tmp_path / "sensor_state.json",
    )
    app.config["TESTING"] = True
    return app


# ---------------------------------------------------------------------------
# Healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_ok(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/healthz/")
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"ok": True, "service": "wildfire-watch-frontend"}


@pytest.mark.parametrize("path", ["/healthz", "/healthz/", "/health", "/health/"])
def test_health_aliases_return_ok(app_with_auth, path):
    client = app_with_auth.test_client()
    r = client.get(path)
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "service": "wildfire-watch-frontend"}


def test_healthz_does_not_require_admin(app_with_auth):
    client = app_with_auth.test_client()
    r = client.get("/healthz/")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def test_index_renders(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "wildfire-watch" in body
    assert "incident workbench" in body
    assert "Operational read" in body
    assert "AOR map" in body
    assert "Fleet readiness" in body
    assert "Runbook" in body
    assert "operator-supervised" in body
    assert 'id="ops-risk"' in body
    assert 'id="ops-action"' in body


def test_frontend_js_updates_operational_brief():
    js = Path("frontend/static/js/dashboard.js").read_text(encoding="utf-8")
    assert "function updateOpsBrief" in js
    assert "highestRiskSignal" in js
    assert "operator review before FD fan-out" in js
    assert "ops-sensors" in js


def test_index_blocked_without_token(app_with_auth):
    client = app_with_auth.test_client()
    r = client.get("/")
    assert r.status_code == 401


def test_index_unlocked_with_token(app_with_auth):
    client = app_with_auth.test_client()
    r = client.get("/", headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /api/signals
# ---------------------------------------------------------------------------


def test_api_signals_returns_rows(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/signals")
    assert r.status_code == 200
    body = r.get_json()
    assert "count" in body
    assert "signals" in body
    assert body["count"] == len(body["signals"])
    assert body["count"] >= 1


def test_api_signals_filter_by_zone(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/signals?zone=cement-creek-drainage")
    assert r.status_code == 200
    body = r.get_json()
    assert body["count"] == 1
    assert body["signals"][0]["zone_id"] == "cement-creek-drainage"


def test_api_signals_filter_min_risk(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/signals?min_risk=90")
    assert r.status_code == 200
    body = r.get_json()
    for s in body["signals"]:
        assert s["risk_score"] >= 90


# ---------------------------------------------------------------------------
# /api/kpis + /api/sensors + /api/aor
# ---------------------------------------------------------------------------


def test_api_kpis_shape(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/kpis")
    assert r.status_code == 200
    body = r.get_json()
    for key in (
        "total",
        "last_24h",
        "last_7d",
        "highest_risk_zone",
        "highest_risk_value",
        "last_heartbeat",
        "retry_queue_depth",
        "by_type",
    ):
        assert key in body


def test_api_sensors_shape(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/sensors")
    assert r.status_code == 200
    body = r.get_json()
    assert "sensors" in body
    assert len(body["sensors"]) >= 1
    for s in body["sensors"]:
        assert s["status"] in {"online", "stale", "down"}


def test_api_aor_returns_geojson(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/aor")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("type") == "FeatureCollection"
    assert isinstance(body.get("features"), list)


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------


def test_compute_kpis_counts_24h_and_7d():
    rows = [
        _sig(minutes_ago=10, risk=80.0),
        _sig(minutes_ago=60 * 24 * 3, risk=20.0),  # 3d
        _sig(minutes_ago=60 * 24 * 9, risk=10.0),  # 9d > 7d
    ]
    k = compute_kpis(rows, retry_depth=2)
    assert k["total"] == 3
    assert k["last_24h"] == 1
    assert k["last_7d"] == 2
    assert k["retry_queue_depth"] == 2


def test_compute_kpis_picks_highest_risk_zone():
    rows = [
        _sig(zone="a", risk=90.0),
        _sig(zone="a", risk=80.0),
        _sig(zone="b", risk=20.0),
    ]
    k = compute_kpis(rows, retry_depth=0)
    assert k["highest_risk_zone"] == "a"
    assert k["highest_risk_value"] == 85.0


def test_compute_sensor_health_status_buckets():
    rows = [
        _sig(drone="wfw-fresh", minutes_ago=5),
        _sig(drone="wfw-stale", minutes_ago=60),
        _sig(drone="wfw-old", minutes_ago=60 * 6),
    ]
    sensors = {s["drone_id"]: s for s in compute_sensor_health(rows)}
    # Default thresholds: online < 30 min < stale < 120 min < down
    assert sensors["wfw-fresh"]["status"] == "online"
    assert sensors["wfw-stale"]["status"] == "stale"
    assert sensors["wfw-old"]["status"] == "down"


def test_filter_signals_limit_and_sort():
    rows = [
        _sig(minutes_ago=10),
        _sig(minutes_ago=200),
        _sig(minutes_ago=30),
    ]
    out = filter_signals(rows, limit=2)
    assert len(out) == 2
    # newest first
    assert out[0]["timestamp"] >= out[1]["timestamp"]


def test_fixture_fallback_when_signals_path_missing(tmp_path: Path, monkeypatch):
    """If signals path is empty/missing, the fixture must populate the dashboard."""
    monkeypatch.setenv("SENSOR_HEALTH_POLL_DISABLED", "1")
    missing = tmp_path / "does_not_exist.jsonl"
    app = create_app(signals_path=missing)
    app.config["TESTING"] = True
    client = app.test_client()
    r = client.get("/api/signals")
    assert r.status_code == 200
    body = r.get_json()
    # bundled fixture has 12 rows
    assert body["count"] >= 1


# ---------------------------------------------------------------------------
# /api/sensors/health + state-change detection
# ---------------------------------------------------------------------------


def test_api_sensors_health_aggregate_shape(app_no_auth):
    client = app_no_auth.test_client()
    r = client.get("/api/sensors/health")
    assert r.status_code == 200
    body = r.get_json()
    for key in (
        "total",
        "online",
        "stale",
        "down",
        "stale_threshold_min",
        "down_threshold_min",
    ):
        assert key in body, key
    assert body["total"] == body["online"] + body["stale"] + body["down"]


def test_api_sensors_health_blocked_without_token(app_with_auth):
    client = app_with_auth.test_client()
    r = client.get("/api/sensors/health")
    assert r.status_code == 401


def test_compute_sensor_health_aggregate_counts():
    from frontend.app import compute_sensor_health_aggregate

    sensors = [
        {"drone_id": "a", "status": "online"},
        {"drone_id": "b", "status": "online"},
        {"drone_id": "c", "status": "stale"},
        {"drone_id": "d", "status": "down"},
    ]
    agg = compute_sensor_health_aggregate(sensors)
    assert agg["total"] == 4
    assert agg["online"] == 2
    assert agg["stale"] == 1
    assert agg["down"] == 1


def test_detect_sensor_state_changes_first_run_no_transitions(tmp_path: Path):
    from frontend.app import detect_sensor_state_changes

    sensors = [{"drone_id": "wfw-a", "status": "online"}]
    state = tmp_path / "state.json"
    transitions = detect_sensor_state_changes(sensors, state)
    # Empty prior state -> nothing is a transition.
    assert transitions == []
    # State was persisted.
    assert state.exists()


def test_detect_sensor_state_changes_emits_on_transition(tmp_path: Path):
    from frontend.app import detect_sensor_state_changes

    state = tmp_path / "state.json"
    detect_sensor_state_changes(
        [{"drone_id": "wfw-a", "status": "online"}], state
    )
    transitions = detect_sensor_state_changes(
        [{"drone_id": "wfw-a", "status": "stale", "last_seen": "2026-05-02T18:00:00Z"}],
        state,
    )
    assert len(transitions) == 1
    assert transitions[0]["drone_id"] == "wfw-a"
    assert transitions[0]["from"] == "online"
    assert transitions[0]["to"] == "stale"


def test_detect_sensor_state_changes_no_transition_when_unchanged(tmp_path: Path):
    from frontend.app import detect_sensor_state_changes

    state = tmp_path / "state.json"
    detect_sensor_state_changes([{"drone_id": "wfw-a", "status": "online"}], state)
    transitions = detect_sensor_state_changes(
        [{"drone_id": "wfw-a", "status": "online"}], state
    )
    assert transitions == []


def test_run_sensor_health_check_returns_envelope(
    tmp_path: Path, monkeypatch, signals_jsonl: Path
):
    """Background poll round-trip — returns transitions + alerts_sent envelope.

    The alerts module is best-effort (lazy-imported in the watcher) so
    this test only verifies the call shape is stable. Whether the
    alert actually pages depends on env vars; the alerts unit tests
    cover that path.
    """
    monkeypatch.setenv("SENSOR_HEALTH_POLL_DISABLED", "1")
    state_path = tmp_path / "state.json"

    app = create_app(signals_path=signals_jsonl, sensor_state_path=state_path)
    result = app.run_sensor_health_check()
    assert isinstance(result, dict)
    assert "transitions" in result
    assert "alerts_sent" in result
    # First run -> empty prior state -> no transitions.
    assert result["transitions"] == []
    assert result["alerts_sent"] == 0


def test_run_sensor_health_check_dispatches_on_transition(
    tmp_path: Path, monkeypatch, signals_jsonl: Path
):
    """Seed prior state, run twice, verify transition is dispatched."""
    monkeypatch.setenv("SENSOR_HEALTH_POLL_DISABLED", "1")
    state_path = tmp_path / "state.json"
    # Seed prior state where wfw-rari1 was 'down'; the fixture data has
    # it 'online' (heartbeat 2 min ago) so this is a clear transition.
    state_path.write_text(
        json.dumps({"wfw-rari1": "down"}), encoding="utf-8"
    )

    app = create_app(signals_path=signals_jsonl, sensor_state_path=state_path)
    result = app.run_sensor_health_check()
    drone_ids = [t["drone_id"] for t in result["transitions"]]
    assert "wfw-rari1" in drone_ids
