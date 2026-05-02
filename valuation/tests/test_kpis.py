"""Tests for valuation.kpis collectors."""

from __future__ import annotations

from valuation import kpis


EXPECTED_KPI_NAMES = {
    # engineering
    "loc_total",
    "loc_tests",
    "tests_passing",
    "tests_files",
    "commits_30d",
    "unique_authors_90d",
    "docs_files",
    "intel_docs_count",
    "code_to_doc_ratio",
    # product
    "signals_emitted_total",
    "signals_emitted_30d",
    "simulator_runs_total",
    "simulated_minutes_total",
    "false_positive_rate_estimate",
    "model_versions_shipped",
    "mission_zones_count",
    # strategic
    "letters_of_authorization_count",
    "partner_agencies_engaged",
    "acquirer_briefings_held",
    "media_mentions_30d",
    # compliance
    "ndaa_blue_uas_eligible",
    "itar_exposure_score",
    "faa_part107_certified_pilots",
    "secrets_in_repo",
}


def test_collect_all_returns_all_expected_keys():
    out = kpis.collect_all()
    assert set(out.keys()) == EXPECTED_KPI_NAMES, (
        f"missing: {EXPECTED_KPI_NAMES - set(out.keys())}, "
        f"extra: {set(out.keys()) - EXPECTED_KPI_NAMES}"
    )


def test_kpi_snapshot_dict_returns_flat_values():
    snap = kpis.kpi_snapshot_dict()
    assert isinstance(snap, dict)
    for k, v in snap.items():
        assert not isinstance(v, kpis.KPI), f"{k} should be unwrapped"


def test_loc_total_is_positive():
    out = kpis.collect_all()
    assert out["loc_total"].value > 0
    assert out["loc_total"].unit == "lines"


def test_tests_passing_collected():
    out = kpis.collect_all()
    # Live repo has tests; just ensure it ran (>=0 is the contract).
    assert out["tests_passing"].value >= 0


def test_secrets_in_repo_should_be_zero():
    """If this fails, rotate keys + clean history before merging."""
    out = kpis.collect_all()
    assert out["secrets_in_repo"].value == 0, (
        "Secret detected in repo. Rotate + remove before commit."
    )


def test_ndaa_blue_uas_reflects_bom():
    """The current BOM at hardware/bom.csv is Holybro/Cube/Jetson — no
    DJI in the row vendors. So the NDAA flag should be True. If you
    add a DJI line it should flip False — but that's tested indirectly
    via the function being source-of-truth."""
    out = kpis.collect_all()
    assert isinstance(out["ndaa_blue_uas_eligible"].value, bool)
    # The phase-1 BOM has no DJI; it should be eligible.
    assert out["ndaa_blue_uas_eligible"].value is True


def test_itar_exposure_score_low_for_civilian():
    out = kpis.collect_all()
    score = out["itar_exposure_score"].value
    assert 0 <= score <= 100
    # Civilian fire-watch project: should be very low. If this fails
    # we've drifted into dual-use territory.
    assert score <= 30, f"ITAR score {score} unexpectedly high for civilian project"


def test_simulator_runs_count_is_nonneg():
    out = kpis.collect_all()
    assert out["simulator_runs_total"].value >= 0


def test_kpi_categories():
    out = kpis.collect_all()
    cats = {kpi.category for kpi in out.values()}
    assert cats == {"engineering", "product", "strategic", "compliance"}
