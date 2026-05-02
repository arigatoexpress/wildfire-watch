"""Tests for valuation.methods."""

from __future__ import annotations

from valuation.comps import Comp
from valuation.methods import (
    asset_floor,
    comparable_multiples,
    consensus_band,
    dcf_lite,
    implicit_revenue,
    venture_method,
)


def _toy_snapshot(**overrides):
    base = {
        "loc_total": 5000,
        "loc_tests": 1500,
        "tests_passing": 80,
        "simulator_runs_total": 2,
        "signals_emitted_total": 154,
        "partner_agencies_engaged": 0,
        "letters_of_authorization_count": 0,
        "ndaa_blue_uas_eligible": True,
        "model_versions_shipped": 0,
        "mission_zones_count": 1,
        "intel_docs_count": 4,
        "faa_part107_certified_pilots": 0,
        "secrets_in_repo": 0,
    }
    base.update(overrides)
    return base


def _toy_comps():
    return [
        Comp(target="A", acquirer=None, date="2024-01-01",
             amount_usd=1e9, revenue_estimate_usd=5e8, multiple=2.0,
             archetype="defense-tech-platform", source="x"),
        Comp(target="B", acquirer=None, date="2024-01-01",
             amount_usd=1e8, revenue_estimate_usd=2e7, multiple=5.0,
             archetype="defense-tech-platform", source="x"),
        Comp(target="C", acquirer=None, date="2024-01-01",
             amount_usd=1e9, revenue_estimate_usd=1e8, multiple=10.0,
             archetype="public-safety-saas", source="x"),
        Comp(target="D", acquirer=None, date="2024-01-01",
             amount_usd=1e9, revenue_estimate_usd=5e7, multiple=20.0,
             archetype="public-safety-saas", source="x"),
        Comp(target="E", acquirer=None, date="2024-01-01",
             amount_usd=1e8, revenue_estimate_usd=2e6, multiple=50.0,
             archetype="small-uas-vendor", source="x"),
    ]


def _check_band(out):
    assert "low" in out and "mid" in out and "high" in out and "rationale" in out
    assert out["low"] <= out["mid"] <= out["high"], out


def test_implicit_revenue_zero_when_empty():
    snap = _toy_snapshot(loc_total=0, simulator_runs_total=0,
                         signals_emitted_total=0, partner_agencies_engaged=0,
                         letters_of_authorization_count=0)
    assert implicit_revenue(snap) == 0.0


def test_comparable_multiples_returns_band():
    out = comparable_multiples(_toy_snapshot(), _toy_comps())
    _check_band(out)
    assert out["archetype"] in (
        "defense-tech-platform",
        "public-safety-saas",
        "drone-in-a-box",
        "small-uas-vendor",
        "computer-vision-defense",
    )


def test_comparable_multiples_picks_public_safety_when_partners_high():
    out = comparable_multiples(
        _toy_snapshot(
            partner_agencies_engaged=3,
            letters_of_authorization_count=2,
        ),
        _toy_comps(),
    )
    assert out["archetype"] == "public-safety-saas"


def test_comparable_multiples_picks_small_uas_when_ndaa_only():
    out = comparable_multiples(
        _toy_snapshot(
            ndaa_blue_uas_eligible=True,
            partner_agencies_engaged=0,
            letters_of_authorization_count=0,
            simulator_runs_total=2,
            mission_zones_count=1,
        ),
        _toy_comps(),
    )
    # With NDAA + no other signals, we should land on small-uas-vendor.
    assert out["archetype"] == "small-uas-vendor"


def test_venture_method_returns_band():
    out = venture_method(_toy_snapshot())
    _check_band(out)
    # P(exit) bounds.
    assert 0 < out["p_acquired_in_5y"] <= 0.95


def test_venture_method_secrets_penalty():
    snap_clean = _toy_snapshot(secrets_in_repo=0)
    snap_dirty = _toy_snapshot(secrets_in_repo=1)
    clean = venture_method(snap_clean)
    dirty = venture_method(snap_dirty)
    assert dirty["p_acquired_in_5y"] < clean["p_acquired_in_5y"]


def test_dcf_lite_returns_band():
    out = dcf_lite(_toy_snapshot())
    _check_band(out)


def test_dcf_lite_grows_with_signals():
    low_sigs = dcf_lite(_toy_snapshot(signals_emitted_total=10))
    high_sigs = dcf_lite(_toy_snapshot(signals_emitted_total=10000))
    # With LOAs=0/partners=0 the y1 is 0; both should be 0 unless we add
    # revenue. Test directly with LOAs.
    low_sigs = dcf_lite(
        _toy_snapshot(letters_of_authorization_count=1, signals_emitted_total=10)
    )
    high_sigs = dcf_lite(
        _toy_snapshot(letters_of_authorization_count=1, signals_emitted_total=10000)
    )
    assert high_sigs["mid"] > low_sigs["mid"]


def test_asset_floor_returns_band():
    out = asset_floor(_toy_snapshot())
    _check_band(out)
    # 5000 LOC total, 1500 tests, 0 pilots
    # novel = 3500 * 150 = 525_000; tests = 1500 * 50 = 75_000; team = 0
    # mid = 600_000
    assert out["mid"] == 600_000


def test_consensus_band_aggregates():
    methods = {
        "comparable_multiples": {"low": 1_000_000, "mid": 5_000_000, "high": 20_000_000},
        "venture_method": {"low": 500_000, "mid": 2_000_000, "high": 5_000_000},
        "dcf_lite": {"low": 0, "mid": 100_000, "high": 1_000_000},
        "asset_floor": {"low": 600_000, "mid": 1_000_000, "high": 1_500_000},
    }
    out = consensus_band(methods)
    assert out["low"] == 0
    assert out["high"] == 20_000_000
    # mid is weighted: 0.4*5M + 0.2*2M + 0.2*0.1M + 0.2*1M
    #               = 2.0M + 0.4M + 0.02M + 0.2M = 2.62M
    assert 2_600_000 <= out["mid"] <= 2_650_000


def test_consensus_band_weights_normalize():
    methods = {
        "comparable_multiples": {"low": 0, "mid": 1000, "high": 10000},
    }
    out = consensus_band(methods, weights={"comparable_multiples": 1.0})
    assert out["mid"] == 1000
