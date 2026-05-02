"""Four valuation methods.

Each method takes a flat KPI snapshot dict + a list of Comp records and
returns a dict with low/mid/high USD figures plus a rationale string.

The methods are deliberately conservative. The intent is to produce a
defensible band, not a number we wave at investors. When uncertainty is
high — and for an asset of this maturity it IS high — the band widens,
not the mid.

Method weights (default 40/20/20/20):
- comparable_multiples — primary signal (real comps in the same sector)
- venture_method      — discounts the strategic-acquisition story
- dcf_lite            — sanity-checks against a forward revenue ramp
- asset_floor         — floor; what would code+team replacement cost?
"""

from __future__ import annotations

from typing import Any

from .comps import Comp, archetype_summary, by_archetype, multiples_for


# Implicit revenue proxy formula (documented):
#
#   implicit_revenue = (
#       (loc_total / 50)               # ~$50/LOC of "value-equivalent revenue"
#       + simulator_runs_total * 1000  # each sim run = $1k of equivalent product activity
#       + signals_emitted_total * 50   # each emitted signal = $50 of equivalent product activity
#       + partner_agencies_engaged * 50000  # each engaged agency = $50k pipeline
#       + letters_of_authorization_count * 250000  # each LOA = $250k of bookable revenue
#   )
#
# This is a PROXY for product readiness, not actual booked revenue. We
# multiply it by comp multiples to get a comparable-bounded valuation.
# The weights are deliberately small for early-stage KPIs — this keeps
# the number honest.
def implicit_revenue(snapshot: dict[str, Any]) -> float:
    loc = snapshot.get("loc_total", 0)
    sim_runs = snapshot.get("simulator_runs_total", 0)
    signals = snapshot.get("signals_emitted_total", 0)
    partners = snapshot.get("partner_agencies_engaged", 0)
    loas = snapshot.get("letters_of_authorization_count", 0)
    return (
        (loc / 50.0)
        + (sim_runs * 1000.0)
        + (signals * 50.0)
        + (partners * 50000.0)
        + (loas * 250000.0)
    )


def _pick_archetype(snapshot: dict[str, Any]) -> str:
    """Heuristic archetype selection based on KPI shape.

    - Heavy partner engagement + LOAs                -> public-safety-saas
    - Many model versions + signals                  -> computer-vision-defense
    - High simulator activity + zones                -> drone-in-a-box
    - NDAA-eligible + small frame                    -> small-uas-vendor
    - Default                                        -> defense-tech-platform
    """
    partners = snapshot.get("partner_agencies_engaged", 0)
    loas = snapshot.get("letters_of_authorization_count", 0)
    models = snapshot.get("model_versions_shipped", 0)
    signals = snapshot.get("signals_emitted_total", 0)
    sim_runs = snapshot.get("simulator_runs_total", 0)
    zones = snapshot.get("mission_zones_count", 0)
    ndaa = snapshot.get("ndaa_blue_uas_eligible", False)

    if (partners + loas) >= 3:
        return "public-safety-saas"
    if models >= 2 and signals >= 100:
        return "computer-vision-defense"
    if sim_runs >= 5 and zones >= 2:
        return "drone-in-a-box"
    if ndaa:
        return "small-uas-vendor"
    return "defense-tech-platform"


def comparable_multiples(
    snapshot: dict[str, Any], comps: list[Comp]
) -> dict[str, Any]:
    """Pick best-matching archetype, apply low/mid/high multiples to
    implicit revenue. Document the picked archetype + multiples used.
    """
    rev = implicit_revenue(snapshot)
    archetype = _pick_archetype(snapshot)

    # Try the picked archetype first; if it has no multiples, fall back
    # to the union of all comps so we don't return zero.
    subset = by_archetype(comps, archetype)
    mults = multiples_for(subset)
    fallback_used = False
    if not mults:
        fallback_used = True
        mults = multiples_for(comps)
    if not mults:
        # Truly no comp data — return a placeholder.
        return {
            "low": 0,
            "mid": 0,
            "high": 0,
            "rationale": "No comps available; valuation skipped.",
            "archetype": archetype,
            "implicit_revenue_usd": rev,
            "multiples_used": (0.0, 0.0, 0.0),
        }

    low_mult = mults[0]
    high_mult = mults[-1]
    mid_mult = mults[len(mults) // 2]

    low = int(rev * low_mult)
    mid = int(rev * mid_mult)
    high = int(rev * high_mult)
    if low > mid:
        low, mid = mid, low
    if mid > high:
        mid, high = high, mid

    rationale = (
        f"archetype={archetype} (n={len(subset)} direct comps"
        f"{', fallback to all comps' if fallback_used else ''}). "
        f"implicit_revenue=${rev:,.0f}; "
        f"multiples low/mid/high={low_mult:.1f}/{mid_mult:.1f}/{high_mult:.1f}."
    )

    return {
        "low": low,
        "mid": mid,
        "high": high,
        "rationale": rationale,
        "archetype": archetype,
        "implicit_revenue_usd": rev,
        "multiples_used": (low_mult, mid_mult, high_mult),
    }


def venture_method(
    snapshot: dict[str, Any],
    *,
    expected_acquisition_value_usd: float = 100_000_000,
    p_acquired_in_5y: float = 0.05,
    required_irr: float = 0.30,
    horizon_years: int = 5,
) -> dict[str, Any]:
    """Classic venture method: discount expected exit by required IRR
    and probability of reaching that exit.

    All four params are configurable so this can be retuned as KPIs
    de-risk the bet (eg. when LOAs land, p_acquired goes up).

    KPI-driven probability adjustment:
      - Each engaged partner adds 1% to p_acquired (cap +10%).
      - Each LOA adds 3% to p_acquired (cap +15%).
      - NDAA eligibility adds 2%.
      - secrets_in_repo > 0 SUBTRACTS 5% (deal-breakers for compliance).
    """
    p = p_acquired_in_5y
    p += min(0.10, snapshot.get("partner_agencies_engaged", 0) * 0.01)
    p += min(0.15, snapshot.get("letters_of_authorization_count", 0) * 0.03)
    if snapshot.get("ndaa_blue_uas_eligible", False):
        p += 0.02
    if snapshot.get("secrets_in_repo", 0) > 0:
        p -= 0.05
    p = max(0.001, min(0.95, p))

    discount = (1 + required_irr) ** horizon_years
    mid = expected_acquisition_value_usd * p / discount
    # Band: +/- 50% on mid.
    low = mid * 0.5
    high = mid * 1.5

    rationale = (
        f"E[exit]=${expected_acquisition_value_usd:,.0f}, "
        f"P(exit)={p:.3f} (KPI-adjusted from {p_acquired_in_5y}), "
        f"IRR={required_irr}, horizon={horizon_years}y, "
        f"discount={discount:.2f}."
    )
    return {
        "low": int(low),
        "mid": int(mid),
        "high": int(high),
        "rationale": rationale,
        "p_acquired_in_5y": p,
        "expected_acquisition_value_usd": expected_acquisition_value_usd,
    }


def dcf_lite(snapshot: dict[str, Any]) -> dict[str, Any]:
    """5-year DCF tied to KPI thresholds.

    Year-by-year revenue is a step function of strategic KPIs:
      - Year 1: $50k per LOA, $5k per engaged partner. Floor at $0.
      - Year 2-5: each year's revenue = max(prior year * (1 + g), floor)
        where g varies with signal volume:
          * <100 signals/yr        -> g = 0.20
          * 100-1000 signals/yr    -> g = 0.40
          * >1000 signals/yr       -> g = 0.80

    Discount rate: 25% (private-tech, pre-revenue-scale).
    Terminal multiple: 5x year-5 revenue (conservative for late-stage).
    """
    loas = snapshot.get("letters_of_authorization_count", 0)
    partners = snapshot.get("partner_agencies_engaged", 0)
    signals = snapshot.get("signals_emitted_total", 0)

    if signals < 100:
        g = 0.20
    elif signals < 1000:
        g = 0.40
    else:
        g = 0.80

    y1 = loas * 50_000 + partners * 5_000
    revenues = [y1]
    for _ in range(4):
        revenues.append(revenues[-1] * (1 + g))

    discount = 0.25
    pv = 0.0
    for i, r in enumerate(revenues, start=1):
        # Free cash flow proxy: 30% of revenue (early-stage software margin assumption).
        fcf = r * 0.30
        pv += fcf / ((1 + discount) ** i)

    terminal = revenues[-1] * 5
    pv += terminal / ((1 + discount) ** 5)

    # If everything's zero, return a zero band rather than nan.
    mid = max(pv, 0.0)
    low = mid * 0.4
    high = mid * 1.8

    rationale = (
        f"y1=${y1:,.0f} (LOAs={loas}, partners={partners}); "
        f"growth={g:.0%} (signals={signals}); "
        f"discount={discount}; terminal=5x*y5; "
        f"5y revenues=[{', '.join(f'${r:,.0f}' for r in revenues)}]"
    )
    return {
        "low": int(low),
        "mid": int(mid),
        "high": int(high),
        "rationale": rationale,
        "yearly_revenues": revenues,
    }


def asset_floor(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Code-asset value: $150/LOC for novel IP, $50/LOC for tests, plus
    team-replacement cost (1 senior eng @ $250k/yr * 0.5y = $125k baseline
    per Part 107 pilot, $0 floor when team is empty).
    """
    loc_total = snapshot.get("loc_total", 0)
    loc_tests = snapshot.get("loc_tests", 0)
    loc_novel = max(0, loc_total - loc_tests)
    pilots = snapshot.get("faa_part107_certified_pilots", 0)

    code_value = loc_novel * 150 + loc_tests * 50
    team_value = pilots * 125_000
    mid = code_value + team_value
    # Floor band is tight: this is what you'd pay for the carcass.
    low = mid * 0.6
    high = mid * 1.2

    rationale = (
        f"novel_loc={loc_novel} @ $150 = ${loc_novel*150:,}; "
        f"test_loc={loc_tests} @ $50 = ${loc_tests*50:,}; "
        f"pilots={pilots} @ $125k = ${pilots*125_000:,}."
    )
    return {
        "low": int(low),
        "mid": int(mid),
        "high": int(high),
        "rationale": rationale,
    }


def consensus_band(
    methods_out: dict[str, dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> dict[str, int]:
    """Aggregate the four method bands into a consensus.

    - low   = min of all method lows
    - high  = max of all method highs
    - mid   = weighted average of method mids
    """
    weights = weights or {
        "comparable_multiples": 0.4,
        "venture_method": 0.2,
        "dcf_lite": 0.2,
        "asset_floor": 0.2,
    }
    lows = [m["low"] for m in methods_out.values()]
    highs = [m["high"] for m in methods_out.values()]
    weighted_mid = 0.0
    weight_sum = 0.0
    for name, m in methods_out.items():
        w = weights.get(name, 0.0)
        weighted_mid += m["mid"] * w
        weight_sum += w
    if weight_sum > 0:
        weighted_mid = weighted_mid / weight_sum
    return {
        "low": int(min(lows)) if lows else 0,
        "mid": int(weighted_mid),
        "high": int(max(highs)) if highs else 0,
    }
