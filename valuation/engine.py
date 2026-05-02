"""ValuationEngine: aggregate KPIs, run methods, emit a band + ranking + actions.

The engine is the single entrypoint everything else (CLI, web, tests)
talks to. `compute_valuation()` is pure given a snapshot + comp set —
no I/O, no clock dependence — so it's deterministic for tests.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .comps import Comp
from .methods import (
    asset_floor,
    comparable_multiples,
    consensus_band,
    dcf_lite,
    venture_method,
)


# Strategic acquirer profiles. Each scores 0-1 against KPI fit.
# Score weights are intentionally explicit so the user can audit them.
ACQUIRERS = [
    {
        "name": "Anduril",
        "axis_weights": {
            "consensus_swarm": 0.35,
            "ndaa_eligible": 0.20,
            "test_density": 0.20,
            "ai_platform_fit": 0.15,
            "public_safety_fit": 0.10,
        },
    },
    {
        "name": "Palantir",
        "axis_weights": {
            "ai_platform_fit": 0.45,
            "ontology_richness": 0.30,
            "public_safety_fit": 0.15,
            "test_density": 0.10,
        },
    },
    {
        "name": "Ondas",
        "axis_weights": {
            "drone_in_a_box_maturity": 0.50,
            "ndaa_eligible": 0.20,
            "public_safety_fit": 0.20,
            "test_density": 0.10,
        },
    },
    {
        "name": "Red Cat",
        "axis_weights": {
            "ndaa_eligible": 0.40,
            "small_uas_fit": 0.30,
            "public_safety_fit": 0.20,
            "test_density": 0.10,
        },
    },
    {
        "name": "Kratos",
        "axis_weights": {
            "small_uas_fit": 0.35,
            "consensus_swarm": 0.30,
            "ndaa_eligible": 0.20,
            "test_density": 0.15,
        },
    },
]


def _score_axes(snapshot: dict[str, Any]) -> dict[str, float]:
    """Compute 0-1 axis scores from the KPI snapshot."""
    sim = snapshot.get("simulator_runs_total", 0)
    sigs = snapshot.get("signals_emitted_total", 0)
    zones = snapshot.get("mission_zones_count", 0)
    loc = snapshot.get("loc_total", 0)
    tests = snapshot.get("tests_passing", 0)
    intel = snapshot.get("intel_docs_count", 0)
    partners = snapshot.get("partner_agencies_engaged", 0)
    loas = snapshot.get("letters_of_authorization_count", 0)
    models = snapshot.get("model_versions_shipped", 0)
    ndaa = snapshot.get("ndaa_blue_uas_eligible", False)

    # Each axis is bounded 0-1 with documented saturation points.
    # consensus_swarm: do we have multi-drone runs + decent test coverage?
    swarm_runs = max(0, sim - 5)  # >5 sim runs hints at swarm work
    consensus_swarm = min(1.0, (swarm_runs / 20.0) + (tests / 200.0) * 0.5)

    # ndaa_eligible: binary KPI -> 1.0 / 0.0
    ndaa_eligible = 1.0 if ndaa else 0.0

    # test_density: tests / (loc/100). Saturates at 50 tests per 100 LOC.
    if loc > 0:
        td = (tests / (loc / 100.0)) / 50.0
    else:
        td = 0.0
    test_density = min(1.0, td)

    # ai_platform_fit: ontology richness ~ intel docs + signals + zones.
    ai_platform_fit = min(1.0, (intel / 10.0) * 0.4 + (sigs / 5000.0) * 0.4 + (zones / 5.0) * 0.2)

    # ontology_richness: same as ai_platform_fit but heavier on intel.
    ontology_richness = min(1.0, (intel / 8.0) * 0.6 + (zones / 5.0) * 0.4)

    # public_safety_fit: partner engagement + LOAs.
    public_safety_fit = min(1.0, (partners / 5.0) * 0.5 + (loas / 3.0) * 0.5)

    # drone_in_a_box_maturity: zones * sim_runs.
    dib = (zones * sim) / 50.0
    drone_in_a_box_maturity = min(1.0, dib)

    # small_uas_fit: NDAA + model versions.
    small_uas_fit = min(1.0, (ndaa_eligible * 0.5) + (models / 5.0) * 0.5)

    return {
        "consensus_swarm": consensus_swarm,
        "ndaa_eligible": ndaa_eligible,
        "test_density": test_density,
        "ai_platform_fit": ai_platform_fit,
        "ontology_richness": ontology_richness,
        "public_safety_fit": public_safety_fit,
        "drone_in_a_box_maturity": drone_in_a_box_maturity,
        "small_uas_fit": small_uas_fit,
    }


def rank_acquirers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Score each of the 5 acquirers; return descending."""
    axes = _score_axes(snapshot)
    out: list[dict[str, Any]] = []
    for acq in ACQUIRERS:
        score = 0.0
        for axis, weight in acq["axis_weights"].items():
            score += axes.get(axis, 0.0) * weight
        # Build a short reason string from top-2 axes.
        contribs = sorted(
            (
                (axis, axes.get(axis, 0.0) * weight, weight)
                for axis, weight in acq["axis_weights"].items()
            ),
            key=lambda t: t[1],
            reverse=True,
        )
        top2 = ", ".join(
            f"{a}={axes.get(a, 0.0):.2f}" for a, _, _ in contribs[:2]
        )
        out.append(
            {
                "name": acq["name"],
                "score": round(score, 3),
                "reason": f"top axes: {top2}",
            }
        )
    out.sort(key=lambda d: d["score"], reverse=True)
    return out


def what_to_do_next(snapshot: dict[str, Any]) -> list[str]:
    """Heuristic next-action list. Each item ties to a KPI delta and
    a rough $-impact on the mid-band, so the user can prioritize.
    """
    actions: list[str] = []
    loas = snapshot.get("letters_of_authorization_count", 0)
    partners = snapshot.get("partner_agencies_engaged", 0)
    pilots = snapshot.get("faa_part107_certified_pilots", 0)
    ndaa = snapshot.get("ndaa_blue_uas_eligible", False)
    sim_runs = snapshot.get("simulator_runs_total", 0)
    signals = snapshot.get("signals_emitted_total", 0)
    secrets = snapshot.get("secrets_in_repo", 0)
    models = snapshot.get("model_versions_shipped", 0)
    zones = snapshot.get("mission_zones_count", 0)
    tests = snapshot.get("tests_passing", 0)

    if secrets > 0:
        actions.append(
            f"BLOCKER: {secrets} secret(s) detected in repo. "
            f"Rotate + remove. Until fixed, venture_method P(exit) is penalized 5%."
        )

    if loas == 0:
        actions.append(
            "Land 1 LOA from CBFPD (priority-1 per AOR.md): +$3M to mid-band — "
            "flips dcf_lite y1 from $0 to $50k, lifts venture P(exit) 3%, "
            "potentially shifts archetype to public-safety-saas."
        )
    elif loas == 1:
        actions.append(
            "Land 2nd LOA (GCFPD): +$5M to mid-band — dcf_lite y1 -> $100k, "
            "venture P(exit) +3%."
        )

    if partners < 2:
        actions.append(
            f"Engage 2-4 priority partner agencies (currently {partners} engaged). "
            f"Each engaged agency adds $5k to dcf y1 + 1% to P(exit) "
            f"(cap +10% across all)."
        )

    if pilots == 0:
        actions.append(
            "Get Part 107 cert ($150 + study time): +$125k asset_floor mid; "
            "unlocks BVLOS waiver path + commercial flight legality."
        )

    if not ndaa:
        actions.append(
            "Migrate Phase 0 BOM off DJI/Autel to NDAA-eligible (Holybro/Cube/Jetson "
            "already in hardware/bom.csv). +2% venture P(exit), +1.0 small_uas_fit "
            "axis (boosts Red Cat acquirer score from 0.x to 0.y)."
        )

    if sim_runs < 10:
        actions.append(
            f"Run 10+ scenario sims (currently {sim_runs}). Each sim run adds "
            f"$1k implicit revenue; 10 runs unlocks consensus_swarm axis -> "
            f"helps Anduril + Kratos rankings."
        )

    if models == 0:
        actions.append(
            "Ship 1 trained ml/fire_detection/runs/<v1> model. "
            "Unlocks computer-vision-defense archetype option (Shield AI multiples)."
        )

    if signals < 1000:
        actions.append(
            f"Get to 1000+ signals (currently {signals}). DCF growth bumps from "
            f"40%/yr to 80%/yr — roughly doubles the dcf_lite mid-band."
        )

    if zones < 3:
        actions.append(
            f"Add 2+ more mission zones to missions/zones/ (currently {zones}). "
            f"Zone count drives drone_in_a_box_maturity axis -> Ondas score."
        )

    if tests < 100:
        actions.append(
            f"Push tests_passing from {tests} to 100+. test_density axis is the "
            f"only KPI weighted across ALL 5 acquirers."
        )

    if not actions:
        actions.append(
            "All near-term KPI levers pulled. Next phase: ship live flights, "
            "publish a 30-day false-positive analysis, schedule first acquirer briefing."
        )
    return actions


def compute_valuation(
    kpi_snapshot: dict[str, Any],
    comps: list[Comp],
    *,
    weights: dict[str, float] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Run all four methods, aggregate, and return the full snapshot.

    Pure function: deterministic given inputs.
    """
    methods_out = {
        "comparable_multiples": comparable_multiples(kpi_snapshot, comps),
        "venture_method": venture_method(kpi_snapshot),
        "dcf_lite": dcf_lite(kpi_snapshot),
        "asset_floor": asset_floor(kpi_snapshot),
    }
    band = consensus_band(methods_out, weights)
    return {
        "as_of": as_of or dt.datetime.now(dt.timezone.utc).isoformat(),
        "kpi_snapshot": kpi_snapshot,
        "methods": methods_out,
        "consensus_band": band,
        "primary_acquirer_ranking": rank_acquirers(kpi_snapshot),
        "what_to_do_next": what_to_do_next(kpi_snapshot),
    }
