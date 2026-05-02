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
def app_no_auth(signals_jsonl: Path):
    os.environ.pop("ADMIN_TOKEN", None)
    app = create_app(signals_path=signals_jsonl)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app_with_auth(signals_jsonl: Path, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    app = create_app(signals_path=signals_jsonl)
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
    assert "Live signal map" in body
    assert "Sensor health" in body
    assert "How to use" in body


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
        assert s["status"] in {"online", "stale", "offline"}


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
    assert sensors["wfw-fresh"]["status"] == "online"
    assert sensors["wfw-stale"]["status"] == "stale"
    assert sensors["wfw-old"]["status"] == "offline"


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


def test_fixture_fallback_when_signals_path_missing(tmp_path: Path):
    """If signals path is empty/missing, the fixture must populate the dashboard."""
    missing = tmp_path / "does_not_exist.jsonl"
    app = create_app(signals_path=missing)
    app.config["TESTING"] = True
    client = app.test_client()
    r = client.get("/api/signals")
    assert r.status_code == 200
    body = r.get_json()
    # bundled fixture has 12 rows
    assert body["count"] >= 1
