"""Tests for valuation.engine."""

from __future__ import annotations

from valuation.comps import Comp
from valuation.engine import compute_valuation, rank_acquirers, what_to_do_next


def _snap(**overrides):
    base = {
        "loc_total": 5000,
        "loc_tests": 1500,
        "tests_passing": 80,
        "tests_files": 10,
        "commits_30d": 10,
        "unique_authors_90d": 2,
        "docs_files": 28,
        "intel_docs_count": 4,
        "code_to_doc_ratio": 0.25,
        "signals_emitted_total": 154,
        "signals_emitted_30d": 154,
        "simulator_runs_total": 2,
        "simulated_minutes_total": 30.0,
        "false_positive_rate_estimate": 0.5,
        "model_versions_shipped": 0,
        "mission_zones_count": 1,
        "letters_of_authorization_count": 0,
        "partner_agencies_engaged": 0,
        "acquirer_briefings_held": 0,
        "media_mentions_30d": 0,
        "ndaa_blue_uas_eligible": True,
        "itar_exposure_score": 5,
        "faa_part107_certified_pilots": 0,
        "secrets_in_repo": 0,
    }
    base.update(overrides)
    return base


def _comps():
    return [
        Comp("A", None, "2024-01-01", 1e9, 5e8, 2.0, "defense-tech-platform", "x"),
        Comp("B", None, "2024-01-01", 1e9, 1e8, 10.0, "defense-tech-platform", "x"),
        Comp("C", None, "2024-01-01", 1e9, 5e7, 20.0, "small-uas-vendor", "x"),
        Comp("D", None, "2024-01-01", 1e9, 2e7, 50.0, "small-uas-vendor", "x"),
        Comp("E", None, "2024-01-01", 1e9, 1e8, 10.0, "public-safety-saas", "x"),
    ]


def test_compute_valuation_shape():
    out = compute_valuation(_snap(), _comps())
    assert "as_of" in out
    assert "kpi_snapshot" in out
    assert "methods" in out
    assert "consensus_band" in out
    assert "primary_acquirer_ranking" in out
    assert "what_to_do_next" in out
    assert set(out["methods"].keys()) == {
        "comparable_multiples",
        "venture_method",
        "dcf_lite",
        "asset_floor",
    }


def test_consensus_band_low_le_mid_le_high():
    out = compute_valuation(_snap(), _comps())
    band = out["consensus_band"]
    assert band["low"] <= band["mid"] <= band["high"], band


def test_acquirer_ranking_has_all_five():
    ranking = rank_acquirers(_snap())
    names = {r["name"] for r in ranking}
    assert names == {"Anduril", "Palantir", "Ondas", "Red Cat", "Kratos"}
    # Sorted descending.
    scores = [r["score"] for r in ranking]
    assert scores == sorted(scores, reverse=True)


def test_acquirer_ranking_ndaa_helps_red_cat():
    ndaa_yes = rank_acquirers(_snap(ndaa_blue_uas_eligible=True))
    ndaa_no = rank_acquirers(_snap(ndaa_blue_uas_eligible=False))
    rc_yes = next(r for r in ndaa_yes if r["name"] == "Red Cat")["score"]
    rc_no = next(r for r in ndaa_no if r["name"] == "Red Cat")["score"]
    assert rc_yes > rc_no


def test_what_to_do_next_has_actionable_items():
    actions = what_to_do_next(_snap())
    assert len(actions) >= 3
    # Every action should be a string with content.
    for a in actions:
        assert isinstance(a, str) and len(a) > 10


def test_what_to_do_next_blocker_for_secrets():
    actions = what_to_do_next(_snap(secrets_in_repo=2))
    # First item should be the blocker.
    assert any("BLOCKER" in a for a in actions)


def test_loa_increases_band():
    base = compute_valuation(_snap(), _comps())
    with_loa = compute_valuation(
        _snap(letters_of_authorization_count=2, partner_agencies_engaged=2),
        _comps(),
    )
    assert (
        with_loa["consensus_band"]["mid"] > base["consensus_band"]["mid"]
    ), "Landing LOAs should raise the mid-band"


def test_compute_valuation_deterministic():
    a = compute_valuation(_snap(), _comps(), as_of="2026-05-01T00:00:00+00:00")
    b = compute_valuation(_snap(), _comps(), as_of="2026-05-01T00:00:00+00:00")
    assert a["consensus_band"] == b["consensus_band"]
    assert a["methods"] == b["methods"]
