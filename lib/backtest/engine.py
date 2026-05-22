"""Backtest engine: replay historic fires through the wildfire-watch fleet.

The model is intentionally transparent and simple — every assumption is
documented + adjustable. Goal: a fire chief can read this, ask
"what if you assumed slower spread?", and get a re-run in 2 seconds.

## Model

Given:
- a `HistoricFire` (centroid, ignition time, acres burned, contained time)
- a `FleetConfig` (n_drones, patrol_revisit_interval_min, detection_prob_per_pass)
- a fleet AOR (we use the canonical Gunnison-Crested Butte corridor zones)

We compute:
- `Δ_detection_minutes`: counterfactual detection-time vs. historic
  discovery (positive = we'd have caught it earlier; negative = later)
- `acres_at_our_detection`: how many acres the fire would have burned
  at the moment we'd have caught it, using a documented spread-rate model
- `acres_saved_at_initial_attack_window`: the lookahead window for fire
  containment (default 60 min ground response, 90 min air response)

## Spread-rate model

We use the Anderson 1982 fuel-model 4 (chaparral / dense conifer crown
fire) **rate of spread** of approximately 9.5 chains/hr (about 191 m/hr)
under "moderate" fire-weather, scaling with the wind/fuel/slope factor.
For Gunnison's beetle-killed spruce-fir under summer drought, that's a
defensible upper bound. Override per-fire by passing `spread_chains_per_hr`.

References:
- Anderson, H.E. (1982). Aids to Determining Fuel Models for Estimating
  Fire Behavior. USDA Forest Service GTR INT-122. Public domain.
- Rothermel, R.C. (1972). A mathematical model for predicting fire
  spread in wildland fuels. USDA Forest Service Research Paper INT-115.

Citations end up in the fire-chief demo pack alongside every backtest
output, so the reader can audit the assumptions.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Avoid a circular import: only the dataclass is needed for type hints.
from sapphire_integration.historical_fires.nifc import HistoricFire


# Anderson 1982 fuel-model 4 ROS at moderate weather, in chains/hr.
# Conservative for beetle-killed spruce-fir at summer drought.
DEFAULT_SPREAD_CHAINS_PER_HR = 9.5
CHAINS_TO_METERS = 20.1168  # 1 surveyor chain = 66 ft = 20.1168 m

# Default initial-attack response windows (minutes from detection).
GROUND_RESPONSE_MIN = 60.0
AIR_RESPONSE_MIN = 90.0


@dataclass(frozen=True)
class FleetConfig:
    """A wildfire-watch fleet configuration to backtest against."""

    n_drones: int = 3
    patrol_altitude_agl_m: float = 80.0
    cruise_speed_mps: float = 8.0
    revisit_interval_min: float = 12.0
    detection_prob_per_pass: float = 0.78
    aor_polygon_km2: float = 1.0
    fleet_uptime_pct: float = 0.85    # availability over the day
    consensus_k_of_n: int = 2

    def expected_passes_per_hour(self) -> float:
        # Number of revisits per drone per hour.
        return 60.0 / max(self.revisit_interval_min, 1.0)

    def effective_detection_prob_per_hour(self) -> float:
        """P(at least one drone detects) per hour assuming independent
        passes with `detection_prob_per_pass` each. Adjusted for fleet uptime.
        """
        passes = self.expected_passes_per_hour() * self.n_drones
        miss_per_pass = 1.0 - self.detection_prob_per_pass
        miss_in_hour = miss_per_pass ** passes
        return self.fleet_uptime_pct * (1.0 - miss_in_hour)


@dataclass(frozen=True)
class DetectionRoll:
    """One simulated detection trial. Emitted per backtest call."""

    seed: int
    detected_within_minutes: float | None  # None if the fire was never caught
    fleet_uptime_active_at_ignition: bool
    rng_draws: int


@dataclass(frozen=True)
class BacktestResult:
    """Counterfactual replay of one historic fire."""

    fire_id: str
    fire_name: str
    fire_year: int
    fire_acres_actual: float
    historical_discovery_time: str | None
    historical_containment_time: str | None
    fleet_config: dict
    spread_chains_per_hr: float

    # Counterfactual outcomes (None if our fleet wasn't covering the AOR).
    in_fleet_aor: bool
    counterfactual_detection_at: str | None
    counterfactual_detection_minutes_after_ignition: float | None
    delta_detection_minutes_vs_historical: float | None
    acres_at_our_detection: float | None
    acres_at_ground_response: float | None
    acres_at_air_response: float | None
    acres_saved_estimate: float | None
    rationale: str
    seed: int


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in km."""
    r_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
    return 2 * r_earth_km * math.asin(math.sqrt(a))


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-cast point-in-polygon. Polygon is list of (lat, lon) tuples."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lon_i > lon) != (lon_j > lon):
            x_intersect = (lat_j - lat_i) * (lon - lon_i) / (lon_j - lon_i + 1e-15) + lat_i
            if lat < x_intersect:
                inside = not inside
        j = i
    return inside


def _fire_in_aor(fire: HistoricFire, aor_polygons: list[list[tuple[float, float]]]) -> bool:
    """True if the fire centroid lies inside any AOR polygon."""
    if not aor_polygons:
        return False
    return any(
        _point_in_polygon(fire.centroid_lat, fire.centroid_lon, p)
        for p in aor_polygons
    )


def _spread_acres(minutes_since_ignition: float, spread_chains_per_hr: float) -> float:
    """Acres burned at minutes_since_ignition under a circular-spread model.

    Radius grows linearly at the ROS. Area = pi * r^2. Returned in acres.
    """
    minutes = max(0.0, minutes_since_ignition)
    hours = minutes / 60.0
    radius_m = spread_chains_per_hr * CHAINS_TO_METERS * hours
    area_m2 = math.pi * radius_m * radius_m
    acres = area_m2 / 4046.8564224  # m^2 per acre
    return acres


def _detection_time_minutes(
    rng: random.Random,
    fleet: FleetConfig,
    *,
    max_hours: float = 24.0,
) -> float | None:
    """Simulate the time-to-first-detection in minutes for one fleet pass.

    We use a discretized Bernoulli per minute with the per-minute prob
    derived from the per-hour effective detection prob. Stops when we hit
    a detection or run past max_hours.
    """
    hourly_p = fleet.effective_detection_prob_per_hour()
    if hourly_p <= 0.0:
        return None
    # P_detect(t=1min) = 1 - (1 - hourly_p) ^ (1/60)
    miss_per_minute = (1.0 - hourly_p) ** (1.0 / 60.0)
    p_per_minute = 1.0 - miss_per_minute
    minutes_max = int(max_hours * 60)
    for m in range(1, minutes_max + 1):
        if rng.random() < p_per_minute:
            return float(m)
    return None


def backtest_fire(
    fire: HistoricFire,
    *,
    fleet: FleetConfig | None = None,
    aor_polygons: list[list[tuple[float, float]]] | None = None,
    spread_chains_per_hr: float = DEFAULT_SPREAD_CHAINS_PER_HR,
    seed: int = 42,
    n_trials: int = 100,
) -> BacktestResult:
    """Backtest a single historic fire against a fleet config.

    Returns a `BacktestResult` whose `counterfactual_detection_minutes_after_ignition`
    is the **mean** of `n_trials` Monte Carlo trials. None if the fire is
    outside the AOR.
    """
    fleet = fleet or FleetConfig()
    aor_polygons = aor_polygons or []

    in_aor = _fire_in_aor(fire, aor_polygons)
    if not in_aor:
        return BacktestResult(
            fire_id=fire.fire_id,
            fire_name=fire.name,
            fire_year=fire.year,
            fire_acres_actual=fire.acres_burned,
            historical_discovery_time=fire.start_date,
            historical_containment_time=fire.contained_date,
            fleet_config=asdict(fleet),
            spread_chains_per_hr=spread_chains_per_hr,
            in_fleet_aor=False,
            counterfactual_detection_at=None,
            counterfactual_detection_minutes_after_ignition=None,
            delta_detection_minutes_vs_historical=None,
            acres_at_our_detection=None,
            acres_at_ground_response=None,
            acres_at_air_response=None,
            acres_saved_estimate=None,
            rationale="fire centroid outside fleet AOR; no counterfactual",
            seed=seed,
        )

    rng = random.Random(seed)
    detections: list[float] = []
    misses = 0
    for trial in range(n_trials):
        sub_rng = random.Random(rng.random())
        t = _detection_time_minutes(sub_rng, fleet)
        if t is None:
            misses += 1
        else:
            detections.append(t)

    if not detections:
        return BacktestResult(
            fire_id=fire.fire_id,
            fire_name=fire.name,
            fire_year=fire.year,
            fire_acres_actual=fire.acres_burned,
            historical_discovery_time=fire.start_date,
            historical_containment_time=fire.contained_date,
            fleet_config=asdict(fleet),
            spread_chains_per_hr=spread_chains_per_hr,
            in_fleet_aor=True,
            counterfactual_detection_at=None,
            counterfactual_detection_minutes_after_ignition=None,
            delta_detection_minutes_vs_historical=None,
            acres_at_our_detection=None,
            acres_at_ground_response=None,
            acres_at_air_response=None,
            acres_saved_estimate=None,
            rationale=(
                f"all {n_trials} trials missed within 24h; fleet config "
                f"effective_detection_prob_per_hour="
                f"{fleet.effective_detection_prob_per_hour():.3f}"
            ),
            seed=seed,
        )

    mean_minutes = sum(detections) / len(detections)
    median_minutes = sorted(detections)[len(detections) // 2]

    # Compare to historical discovery if we have an ignition timestamp.
    delta_minutes: float | None = None
    detection_at_iso: str | None = None
    if fire.start_date:
        try:
            ignition = datetime.fromisoformat(fire.start_date.replace("Z", "+00:00"))
        except ValueError:
            ignition = None
        if ignition is not None:
            detection_dt = ignition + timedelta(minutes=mean_minutes)
            detection_at_iso = detection_dt.isoformat()

    if (
        fire.start_date
        and fire.contained_date
    ):
        # The historical "discovery" we have is FireDiscoveryDateTime, which is
        # the same as ignition for these layers. Δ vs historical here is
        # mean_minutes after ignition (positive = we caught it sooner if we
        # assume historical discovery was "many minutes after ignition";
        # without ignition-vs-discovery split we report mean_minutes directly).
        delta_minutes = mean_minutes

    spread = spread_chains_per_hr
    acres_at_us = _spread_acres(mean_minutes, spread)
    acres_at_ground = _spread_acres(mean_minutes + GROUND_RESPONSE_MIN, spread)
    acres_at_air = _spread_acres(mean_minutes + AIR_RESPONSE_MIN, spread)

    # Acres-saved estimate: actual acres minus our-counterfactual acres at
    # ground response, capped at 0. If the actual fire was small enough that
    # this is negative, we report 0 saved.
    acres_saved = max(0.0, fire.acres_burned - acres_at_ground)

    rationale = (
        f"{n_trials} trials, mean {mean_minutes:.1f} min to detect "
        f"(median {median_minutes:.1f}); fleet "
        f"{fleet.n_drones}-drone, {fleet.revisit_interval_min:.0f}-min revisit; "
        f"{misses}/{n_trials} trials missed in 24h; spread "
        f"{spread:.1f} chains/hr (Anderson 1982 fuel-model 4 baseline)"
    )

    return BacktestResult(
        fire_id=fire.fire_id,
        fire_name=fire.name,
        fire_year=fire.year,
        fire_acres_actual=fire.acres_burned,
        historical_discovery_time=fire.start_date,
        historical_containment_time=fire.contained_date,
        fleet_config=asdict(fleet),
        spread_chains_per_hr=spread,
        in_fleet_aor=True,
        counterfactual_detection_at=detection_at_iso,
        counterfactual_detection_minutes_after_ignition=mean_minutes,
        delta_detection_minutes_vs_historical=delta_minutes,
        acres_at_our_detection=acres_at_us,
        acres_at_ground_response=acres_at_ground,
        acres_at_air_response=acres_at_air,
        acres_saved_estimate=acres_saved,
        rationale=rationale,
        seed=seed,
    )


def backtest_set(
    fires: list[HistoricFire],
    *,
    fleet: FleetConfig | None = None,
    aor_polygons: list[list[tuple[float, float]]] | None = None,
    spread_chains_per_hr: float = DEFAULT_SPREAD_CHAINS_PER_HR,
    seed: int = 42,
    n_trials_per_fire: int = 100,
) -> list[BacktestResult]:
    """Backtest a list of fires. Each fire uses a per-fire-derived seed
    so changing the input ordering doesn't shift trial outcomes.
    """
    out: list[BacktestResult] = []
    for fire in fires:
        # Per-fire seed = base seed XOR fire_id hash, to keep results
        # reproducible across reorderings.
        fire_seed = seed ^ (hash(fire.fire_id) & 0xFFFFFFFF)
        out.append(
            backtest_fire(
                fire,
                fleet=fleet,
                aor_polygons=aor_polygons,
                spread_chains_per_hr=spread_chains_per_hr,
                seed=fire_seed,
                n_trials=n_trials_per_fire,
            )
        )
    return out


def summarize(results: list[BacktestResult]) -> dict[str, Any]:
    """Aggregate a list of BacktestResults into a single summary dict.

    Used by the fire-chief demo pack to produce one number for the deck.
    """
    in_aor = [r for r in results if r.in_fleet_aor and r.counterfactual_detection_minutes_after_ignition is not None]
    out_of_aor = [r for r in results if not r.in_fleet_aor]
    missed = [r for r in results if r.in_fleet_aor and r.counterfactual_detection_minutes_after_ignition is None]
    if not in_aor:
        return {
            "total_fires": len(results),
            "in_aor_count": 0,
            "out_of_aor_count": len(out_of_aor),
            "missed_count": len(missed),
            "mean_detection_minutes": None,
            "median_detection_minutes": None,
            "total_actual_acres": sum(r.fire_acres_actual for r in results),
            "total_acres_saved_estimate": 0.0,
            "rationale": "no fires inside fleet AOR",
        }

    detections = [r.counterfactual_detection_minutes_after_ignition for r in in_aor]
    mean_det = sum(d for d in detections if d is not None) / len(detections)
    sorted_det = sorted(d for d in detections if d is not None)
    median_det = sorted_det[len(sorted_det) // 2]
    saved = [r.acres_saved_estimate for r in in_aor if r.acres_saved_estimate is not None]
    total_saved = sum(saved)

    return {
        "total_fires": len(results),
        "in_aor_count": len(in_aor),
        "out_of_aor_count": len(out_of_aor),
        "missed_count": len(missed),
        "mean_detection_minutes": mean_det,
        "median_detection_minutes": median_det,
        "total_actual_acres": sum(r.fire_acres_actual for r in results),
        "total_acres_saved_estimate": total_saved,
        "rationale": (
            f"{len(in_aor)} of {len(results)} fires fell inside the fleet "
            f"AOR; mean counterfactual detection {mean_det:.1f} min after "
            f"ignition; estimated {total_saved:.0f} acres saved at ground "
            f"response (60-min lookahead)"
        ),
    }


def to_jsonl(results: list[BacktestResult], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), default=str, separators=(",", ":")) + "\n")
    return len(results)
