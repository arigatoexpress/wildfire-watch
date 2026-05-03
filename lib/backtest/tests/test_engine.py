"""Tests for the backtest engine. Pure stdlib + offline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lib.backtest import engine  # noqa: E402
from sapphire_integration.historical_fires import nifc  # noqa: E402


# -----------------------------------------------------------------------
# Math
# -----------------------------------------------------------------------


def test_haversine_zero_at_same_point() -> None:
    assert engine._haversine_km(38.9, -107.0, 38.9, -107.0) == pytest.approx(0.0, abs=1e-9)


def test_haversine_one_degree_lat_about_111_km() -> None:
    d = engine._haversine_km(38.0, -107.0, 39.0, -107.0)
    assert 110 < d < 112


def test_point_in_polygon_inside() -> None:
    poly = [(38.0, -107.0), (38.0, -106.0), (39.0, -106.0), (39.0, -107.0)]
    assert engine._point_in_polygon(38.5, -106.5, poly) is True


def test_point_in_polygon_outside() -> None:
    poly = [(38.0, -107.0), (38.0, -106.0), (39.0, -106.0), (39.0, -107.0)]
    assert engine._point_in_polygon(40.0, -106.5, poly) is False


def test_spread_acres_zero_at_zero_min() -> None:
    assert engine._spread_acres(0.0, engine.DEFAULT_SPREAD_CHAINS_PER_HR) == pytest.approx(0.0, abs=1e-6)


def test_spread_acres_grows_with_time() -> None:
    a30 = engine._spread_acres(30, engine.DEFAULT_SPREAD_CHAINS_PER_HR)
    a60 = engine._spread_acres(60, engine.DEFAULT_SPREAD_CHAINS_PER_HR)
    a120 = engine._spread_acres(120, engine.DEFAULT_SPREAD_CHAINS_PER_HR)
    # Quadratic growth (area = pi r^2, r linear in t)
    assert a30 > 0
    assert a60 / a30 == pytest.approx(4.0, rel=1e-4)
    assert a120 / a60 == pytest.approx(4.0, rel=1e-4)


# -----------------------------------------------------------------------
# FleetConfig
# -----------------------------------------------------------------------


def test_default_fleet_config_reasonable() -> None:
    fc = engine.FleetConfig()
    assert fc.n_drones == 3
    assert fc.revisit_interval_min == 12.0
    p = fc.effective_detection_prob_per_hour()
    assert 0.0 < p < 1.0


def test_more_drones_higher_detection_prob() -> None:
    one = engine.FleetConfig(n_drones=1).effective_detection_prob_per_hour()
    five = engine.FleetConfig(n_drones=5).effective_detection_prob_per_hour()
    assert five > one


def test_zero_drones_zero_prob() -> None:
    p = engine.FleetConfig(n_drones=0).effective_detection_prob_per_hour()
    # 0 drones means 0 passes, so miss prob is 1.0, effective detection is 0.
    assert p == pytest.approx(0.0, abs=1e-6)


# -----------------------------------------------------------------------
# Single-fire backtest
# -----------------------------------------------------------------------


def _aor_polygon_around(fire) -> list[list[tuple[float, float]]]:
    """A 2-degree square AOR centered on the fire centroid."""
    lat, lon = fire.centroid_lat, fire.centroid_lon
    poly = [
        (lat - 1, lon - 1), (lat - 1, lon + 1),
        (lat + 1, lon + 1), (lat + 1, lon - 1),
    ]
    return [poly]


def _aor_polygon_far_from(fire) -> list[list[tuple[float, float]]]:
    """A 2-degree square AOR somewhere very far from the fire."""
    return [[
        (-30.0, 30.0), (-30.0, 32.0),
        (-28.0, 32.0), (-28.0, 30.0),
    ]]


def test_backtest_fire_in_aor_returns_detection() -> None:
    fires = nifc.load_fixture()
    fire = fires[0]
    result = engine.backtest_fire(fire, aor_polygons=_aor_polygon_around(fire), n_trials=50)
    assert result.in_fleet_aor is True
    assert result.counterfactual_detection_minutes_after_ignition is not None
    assert result.counterfactual_detection_minutes_after_ignition > 0
    assert result.acres_at_our_detection is not None


def test_backtest_fire_out_of_aor_no_detection() -> None:
    fires = nifc.load_fixture()
    fire = fires[0]
    result = engine.backtest_fire(fire, aor_polygons=_aor_polygon_far_from(fire), n_trials=50)
    assert result.in_fleet_aor is False
    assert result.counterfactual_detection_minutes_after_ignition is None
    assert result.acres_saved_estimate is None
    assert "outside fleet AOR" in result.rationale


def test_backtest_fire_deterministic_given_seed() -> None:
    fires = nifc.load_fixture()
    fire = fires[0]
    aor = _aor_polygon_around(fire)
    a = engine.backtest_fire(fire, aor_polygons=aor, seed=42, n_trials=50)
    b = engine.backtest_fire(fire, aor_polygons=aor, seed=42, n_trials=50)
    assert (
        a.counterfactual_detection_minutes_after_ignition
        == b.counterfactual_detection_minutes_after_ignition
    )


def test_backtest_fire_rng_changes_with_seed() -> None:
    fires = nifc.load_fixture()
    fire = fires[0]
    aor = _aor_polygon_around(fire)
    a = engine.backtest_fire(fire, aor_polygons=aor, seed=1, n_trials=50)
    b = engine.backtest_fire(fire, aor_polygons=aor, seed=2, n_trials=50)
    # Different seeds should produce different mean detection times
    # (with 50 trials the means are still close, but not identical).
    assert (
        a.counterfactual_detection_minutes_after_ignition
        != b.counterfactual_detection_minutes_after_ignition
    )


# -----------------------------------------------------------------------
# Set-level backtest + summary
# -----------------------------------------------------------------------


def test_backtest_set_returns_one_result_per_fire() -> None:
    fires = nifc.load_fixture()
    aor = _aor_polygon_around(fires[0])
    results = engine.backtest_set(fires, aor_polygons=aor, n_trials_per_fire=20)
    assert len(results) == len(fires)


def test_summarize_with_no_fires_in_aor() -> None:
    fires = nifc.load_fixture()
    aor = _aor_polygon_far_from(fires[0])
    results = engine.backtest_set(fires, aor_polygons=aor, n_trials_per_fire=20)
    summary = engine.summarize(results)
    assert summary["in_aor_count"] == 0
    assert summary["mean_detection_minutes"] is None
    assert summary["total_acres_saved_estimate"] == 0.0


def test_summarize_with_all_fires_in_aor() -> None:
    fires = nifc.load_fixture()
    # Big polygon covering all 3 fires
    aor = [[(38.0, -108.0), (38.0, -106.0), (40.0, -106.0), (40.0, -108.0)]]
    results = engine.backtest_set(fires, aor_polygons=aor, n_trials_per_fire=20)
    summary = engine.summarize(results)
    assert summary["in_aor_count"] == 3
    assert summary["mean_detection_minutes"] is not None
    assert summary["total_acres_saved_estimate"] >= 0.0


def test_to_jsonl_roundtrip(tmp_path: Path) -> None:
    fires = nifc.load_fixture()
    aor = _aor_polygon_around(fires[0])
    results = engine.backtest_set(fires, aor_polygons=aor, n_trials_per_fire=10)
    out = tmp_path / "results.jsonl"
    n = engine.to_jsonl(results, out)
    assert n == 3
    text = out.read_text(encoding="utf-8")
    assert text.count("\n") == 3
