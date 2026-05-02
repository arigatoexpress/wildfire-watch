"""Tests for sim.swarm.consensus."""

from __future__ import annotations

from sim.swarm.consensus import ConsensusConfig, ConsensusVoter


def _signal(
    *,
    drone_id: str,
    lat: float,
    lon: float,
    signal_type: str = "smoke",
    confidence: float = 0.85,
    risk_score: float = 75.0,
    recommended_action: str = "notify_operator",
) -> dict:
    return {
        "schema_version": "1.0.0",
        "signal_id": f"sig-{drone_id}",
        "drone_id": drone_id,
        "zone_id": "test-zone",
        "timestamp": "2026-01-01T00:00:00Z",
        "coords": {
            "lat": lat,
            "lon": lon,
            "alt_agl_m": 80.0,
            "alt_msl_m": 2823.0,
            "heading_deg": 90.0,
            "ground_speed_mps": 6.0,
        },
        "target_coords": {
            "lat": lat,
            "lon": lon,
            "estimation_method": "visual_geolocation",
            "horizontal_uncertainty_m": 15.0,
        },
        "signal_type": signal_type,
        "confidence": confidence,
        "evidence": {
            "frame_uris": ["file:///tmp/x.jpg"],
            "model_outputs": {"rgb_yolo_score": 0.9, "thermal_delta_c": 18.0},
        },
        "risk_score": risk_score,
        "recommended_action": recommended_action,
        "geofence_status": {
            "in_authorized_zone": True,
            "tfr_active": False,
            "remote_id_active": True,
        },
    }


def test_three_drones_same_target_within_window_fires():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0)
    s2 = _signal(drone_id="d2", lat=38.910001, lon=-107.000001)
    s3 = _signal(drone_id="d3", lat=38.9100015, lon=-107.0)

    out1 = voter.submit(s1, emitter_drone_id="d1", sim_time_s=10.0)
    out2 = voter.submit(s2, emitter_drone_id="d2", sim_time_s=11.0)
    # 2-of-3 should fire on submission 2.
    assert out1 is None
    assert out2 is not None

    assert out2["consensus"]["peer_confirmations"] == 2
    assert sorted(out2["consensus"]["peer_drone_ids"]) == ["d1", "d2"]

    # Subsequent emit should NOT re-fire the same cluster.
    out3 = voter.submit(s3, emitter_drone_id="d3", sim_time_s=12.0)
    assert out3 is None
    assert voter.consensus_emitted_count == 1


def test_single_witness_does_not_fire():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    out = voter.submit(
        _signal(drone_id="d1", lat=38.910, lon=-107.0),
        emitter_drone_id="d1",
        sim_time_s=5.0,
    )
    assert out is None
    assert voter.consensus_emitted_count == 0


def test_two_drones_outside_radius_do_not_fire():
    """Two drones reporting events 500 m apart should NOT fire k=2."""
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0)
    # 500 m east-ish (0.005 deg lon at this latitude is ~430 m).
    s2 = _signal(drone_id="d2", lat=38.910, lon=-106.9945)
    out1 = voter.submit(s1, emitter_drone_id="d1", sim_time_s=5.0)
    out2 = voter.submit(s2, emitter_drone_id="d2", sim_time_s=6.0)
    assert out1 is None
    assert out2 is None


def test_two_drones_outside_temporal_window_do_not_fire():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0)
    s2 = _signal(drone_id="d2", lat=38.910, lon=-107.0)
    out1 = voter.submit(s1, emitter_drone_id="d1", sim_time_s=5.0)
    # 120 s later — well outside the 60 s window.
    out2 = voter.submit(s2, emitter_drone_id="d2", sim_time_s=125.0)
    assert out1 is None
    assert out2 is None


def test_recommended_action_escalates_one_tier():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0,
                 recommended_action="notify_operator")
    s2 = _signal(drone_id="d2", lat=38.910, lon=-107.0,
                 recommended_action="notify_operator")
    voter.submit(s1, emitter_drone_id="d1", sim_time_s=1.0)
    out = voter.submit(s2, emitter_drone_id="d2", sim_time_s=2.0)
    assert out is not None
    # notify_operator -> notify_fire_dept (one tier up the ladder).
    assert out["recommended_action"] == "notify_fire_dept"


def test_risk_score_bumped():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0, risk_score=50.0)
    s2 = _signal(drone_id="d2", lat=38.910, lon=-107.0, risk_score=50.0)
    voter.submit(s1, emitter_drone_id="d1", sim_time_s=1.0)
    out = voter.submit(s2, emitter_drone_id="d2", sim_time_s=2.0)
    assert out is not None
    # +20 cap, so 50 -> 70.
    assert out["risk_score"] == 70.0


def test_risk_score_caps_at_100():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0, risk_score=95.0)
    s2 = _signal(drone_id="d2", lat=38.910, lon=-107.0, risk_score=95.0)
    voter.submit(s1, emitter_drone_id="d1", sim_time_s=1.0)
    out = voter.submit(s2, emitter_drone_id="d2", sim_time_s=2.0)
    assert out is not None
    # min(20, 100-95) = 5; 95+5 = 100.
    assert out["risk_score"] == 100.0


def test_consensus_subtype_set():
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0)
    s2 = _signal(drone_id="d2", lat=38.910, lon=-107.0)
    voter.submit(s1, emitter_drone_id="d1", sim_time_s=1.0)
    out = voter.submit(s2, emitter_drone_id="d2", sim_time_s=2.0)
    assert out is not None
    assert out["signal_subtype"] == "sim/consensus_confirmed"


def test_strictest_type_picked():
    """A 'fire' + 'smoke' cluster should yield 'fire' as the canonical
    type because fire is stricter (lower rank) on the ladder."""
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0, signal_type="smoke")
    s2 = _signal(drone_id="d2", lat=38.910, lon=-107.0, signal_type="fire")
    voter.submit(s1, emitter_drone_id="d1", sim_time_s=1.0)
    out = voter.submit(s2, emitter_drone_id="d2", sim_time_s=2.0)
    assert out is not None
    assert out["signal_type"] == "fire"


def test_same_drone_emits_dont_double_count():
    """Two emits from the SAME drone should not satisfy k=2."""
    voter = ConsensusVoter(ConsensusConfig(k=2, r_spatial_m=75.0, t_window_s=60.0))
    s1 = _signal(drone_id="d1", lat=38.910, lon=-107.0)
    s2 = _signal(drone_id="d1", lat=38.910, lon=-107.0)
    out1 = voter.submit(s1, emitter_drone_id="d1", sim_time_s=1.0)
    out2 = voter.submit(s2, emitter_drone_id="d1", sim_time_s=2.0)
    assert out1 is None
    assert out2 is None
