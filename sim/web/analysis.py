"""Post-flight analysis for wildfire-watch sim flights.

Reads ``flight_log.jsonl`` + ``signals.jsonl`` from a flight directory and
returns a dict of derived metrics: total path length, area covered, signal
counts by type and priority, fusion-gate hit-rate, etc.

Pure stdlib. Flask is **lazy-imported** in the CLI block so this module is
runnable from the command line without flask installed.

Coverage area choice: we report the bounding-box area of the flown polyline
in km^2. It's a fast, deterministic upper bound on convex-hull area and
doesn't drag in shapely. Documented in :func:`bounding_box_km2`.

CLI:

    python3 -m sim.web.analysis <flight_dir>
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

EARTH_R_M = 6_371_008.8

# Map recommended_action -> a "priority" label for the dashboard summary.
# (The schema doesn't define priority directly; this is a UI-side convenience.)
_ACTION_PRIORITY = {
    "log_only": "p4",
    "notify_operator": "p3",
    "loiter_and_capture": "p2",
    "notify_fire_dept": "p1",
    "rtl": "p1",
}


# ---------------------------------------------------------------------------
# Geometry helpers — duplicated from sim/kinematics.py to keep this file
# importable on its own without the broader sim package.
# ---------------------------------------------------------------------------


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * EARTH_R_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def path_length_m(points: Iterable[Tuple[float, float]]) -> float:
    """Sum of haversine segments along a sequence of (lat, lon) points."""
    total = 0.0
    prev: Optional[Tuple[float, float]] = None
    for p in points:
        if prev is not None:
            total += haversine_m(prev[0], prev[1], p[0], p[1])
        prev = p
    return total


def bounding_box_km2(points: List[Tuple[float, float]]) -> float:
    """Lat/lon bounding-box area in km^2.

    Approximation: width = haversine across the lat-mid line at lon-min..lon-max,
    height = haversine along a meridian from lat-min..lat-max. This is fast and
    avoids a shapely dependency. It's an over-estimate (loose upper bound) of
    coverage; if SIM-A wants tighter bounds later, swap in a convex hull.
    """
    if len(points) < 2:
        return 0.0
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    lat_mid = (lat_min + lat_max) / 2.0
    width_m = haversine_m(lat_mid, lon_min, lat_mid, lon_max)
    height_m = haversine_m(lat_min, 0.0, lat_max, 0.0)
    return (width_m * height_m) / 1_000_000.0


# ---------------------------------------------------------------------------
# JSONL reading
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file into a list of dicts. Missing file -> []."""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Soft-fail on a corrupt line so partial flights still summarize.
                continue
    return out


def read_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def summarize(flight_dir: Path) -> Dict[str, Any]:
    """Compute post-flight metrics for a flight directory.

    Returns a JSON-serializable dict. Numbers are rounded to keep the
    dashboard tidy; raw values remain available in the JSONL files.
    """
    flight_dir = Path(flight_dir)
    manifest = read_manifest(flight_dir / "manifest.json")
    log = read_jsonl(flight_dir / "flight_log.jsonl")
    signals = read_jsonl(flight_dir / "signals.jsonl")

    points: List[Tuple[float, float]] = [
        (row["lat"], row["lon"]) for row in log if "lat" in row and "lon" in row
    ]
    path_m = path_length_m(points)
    area_km2 = bounding_box_km2(points)

    # Battery + alt + speed roll-ups
    battery_start = log[0].get("battery_pct") if log else None
    battery_end = log[-1].get("battery_pct") if log else None
    if battery_start is not None and battery_end is not None:
        battery_consumed_pct = round(battery_start - battery_end, 1)
    else:
        battery_consumed_pct = 0.0
    max_alt_agl_m = max((r.get("alt_agl_m", 0.0) for r in log), default=0.0)
    speeds = [r.get("speed_mps", 0.0) for r in log if r.get("speed_mps") is not None]
    mean_speed_mps = round(sum(speeds) / len(speeds), 2) if speeds else 0.0

    # Fusion-gate metrics: an "approach" = transition into rgb_score>0.4 OR
    # thermal_delta_c>3 (a candidate the gate is considering); a "hit" = the
    # transition reaches gate.open=True. hit-rate = hits / approaches.
    approaches = 0
    hits = 0
    in_approach = False
    in_hit_window = False
    open_count = 0
    for r in log:
        gs = r.get("gate_state") or {}
        candidate = (gs.get("rgb_score", 0.0) > 0.4) or (gs.get("thermal_delta_c", 0.0) > 3.0)
        is_open = bool(gs.get("open", False))
        if is_open:
            open_count += 1
        if candidate and not in_approach:
            in_approach = True
            approaches += 1
            in_hit_window = False
        if not candidate and in_approach:
            in_approach = False
        if in_approach and is_open and not in_hit_window:
            in_hit_window = True
            hits += 1
    gate_open_rate = round(open_count / len(log), 4) if log else 0.0
    gate_hit_rate = round(hits / approaches, 3) if approaches else 0.0

    # Signal roll-ups
    by_type = Counter()
    by_priority = Counter()
    max_risk = 0.0
    for s in signals:
        by_type[s.get("signal_type", "unknown")] += 1
        prio = _ACTION_PRIORITY.get(s.get("recommended_action", ""), "p4")
        by_priority[prio] += 1
        max_risk = max(max_risk, float(s.get("risk_score", 0.0)))

    return {
        "flight_id": flight_dir.name,
        "mission_name": manifest.get("mission_name"),
        "scenario_name": manifest.get("scenario_name"),
        "started_at": manifest.get("started_at"),
        "ended_at": manifest.get("ended_at"),
        "duration_s": manifest.get("duration_s") or (len(log) if log else 0),
        "row_count": len(log),
        "path_length_km": round(path_m / 1000.0, 3),
        "area_covered_km2": round(area_km2, 3),
        "signals_total": len(signals),
        "signals_by_type": dict(by_type),
        "signals_by_priority": dict(by_priority),
        "max_risk_score": round(max_risk, 1),
        "gate_open_rate": gate_open_rate,
        "gate_approaches": approaches,
        "gate_hits": hits,
        "gate_hit_rate": gate_hit_rate,
        "battery_consumed_pct": battery_consumed_pct,
        "max_alt_agl_m": round(max_alt_agl_m, 1),
        "mean_speed_mps": mean_speed_mps,
    }


# ---------------------------------------------------------------------------
# CLI entry point — flask is lazy-imported so this module runs standalone.
# ---------------------------------------------------------------------------


def _main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m sim.web.analysis <flight_dir>", file=sys.stderr)
        return 2
    summary = summarize(Path(argv[1]))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
