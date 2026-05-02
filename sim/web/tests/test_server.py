"""Flask test-client coverage of the read-only API surface."""
from __future__ import annotations

import json

# Required fields per the wildfire_signal v1 schema.
_SIGNAL_REQUIRED = {
    "signal_id", "drone_id", "zone_id", "timestamp", "coords",
    "signal_type", "confidence", "evidence", "risk_score",
    "recommended_action", "schema_version",
}


def test_healthz(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "wildfire-watch sim viewer" in body
    assert "leaflet" in body.lower()


def test_flights_list_includes_fixture(client):
    r = client.get("/api/flights")
    assert r.status_code == 200
    flights = r.get_json()
    assert isinstance(flights, list)
    assert len(flights) >= 1
    fixture = next(
        (f for f in flights if f["flight_id"] == "fixture:sample_flight"),
        None,
    )
    assert fixture is not None
    assert fixture["mission_name"]
    assert fixture["signals_count"] >= 1


def test_manifest(client):
    r = client.get("/api/flights/fixture:sample_flight/manifest")
    assert r.status_code == 200
    m = r.get_json()
    assert m["mission_name"] == "demo_patrol_alpha"
    assert m["airframe"] == "mavic_mini_2"
    assert len(m["waypoints"]) == 4
    assert len(m["geofence_polygon"]) >= 3


def test_flight_log_returns_rows(client):
    r = client.get("/api/flights/fixture:sample_flight/flight_log")
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) > 30
    row = rows[0]
    for k in ("ts", "lat", "lon", "alt_agl_m", "heading_deg", "battery_pct", "gate_state"):
        assert k in row, f"missing flight_log key: {k}"
    assert "rgb_score" in row["gate_state"]


def test_flight_log_pagination(client):
    """`?limit=` truncates and `?since=` skips earlier rows."""
    r_all = client.get("/api/flights/fixture:sample_flight/flight_log").get_json()
    r_lim = client.get("/api/flights/fixture:sample_flight/flight_log?limit=10").get_json()
    assert len(r_lim) == 10
    pivot = r_all[20]["ts"]
    r_since = client.get(
        f"/api/flights/fixture:sample_flight/flight_log?since={pivot}"
    ).get_json()
    assert all(row["ts"] > pivot for row in r_since)


def test_signals_conform_to_schema(client):
    r = client.get("/api/flights/fixture:sample_flight/signals")
    assert r.status_code == 200
    sigs = r.get_json()
    assert len(sigs) >= 1
    for s in sigs:
        missing = _SIGNAL_REQUIRED - set(s.keys())
        assert not missing, f"signal missing required fields: {missing}"
        assert s["schema_version"] == "1.0.0"
        assert 0.0 <= s["confidence"] <= 1.0
        assert 0.0 <= s["risk_score"] <= 100.0
        assert s["signal_type"] in {
            "smoke", "fire", "thermal_anomaly", "wildlife", "anomaly", "system_event",
        }


def test_analysis(client):
    r = client.get("/api/flights/fixture:sample_flight/analysis")
    assert r.status_code == 200
    a = r.get_json()
    assert a["signals_total"] >= 1
    assert a["path_length_km"] > 0
    assert a["area_covered_km2"] >= 0
    assert a["max_alt_agl_m"] > 0
    assert "smoke" in a["signals_by_type"]


def test_unknown_flight_404s(client):
    r = client.get("/api/flights/does-not-exist/manifest")
    assert r.status_code == 404


def test_flight_id_traversal_blocked(client):
    """Path-separators and parent traversal in flight_id must 404, not leak."""
    r = client.get("/api/flights/..%2Fetc%2Fpasswd/manifest")
    # Flask routing should reject the slash entirely; we get 404 either way.
    assert r.status_code in (404, 400)


def test_replay_streams_event_stream(client):
    """The SSE endpoint sets the right MIME type and yields at least one tick."""
    r = client.get("/api/flights/fixture:sample_flight/replay?speed=200", buffered=False)
    assert r.status_code == 200
    assert r.mimetype == "text/event-stream"
    # Pull a small chunk; the buffered=False client iterates the generator lazily.
    seen = b""
    for chunk in r.response:
        seen += chunk
        if b"event: tick" in seen:
            break
        if len(seen) > 8192:
            break
    r.close()
    assert b"event: tick" in seen
