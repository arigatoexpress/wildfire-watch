# Copyright 2026 wildfire-watch contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# See the LICENSE file in the repo root for the full text.
"""Single-file HTML report renderer for a wildfire-watch flight directory.

Reads ``manifest.json`` + ``flight_log.jsonl`` (or ``drones.jsonl``) +
``signals.jsonl`` (+ ``consensus.jsonl`` if present) and produces one
self-contained HTML file with everything inlined: CSS, SVG icons, the
map, the fusion-gate plot, and the signal table.

Design constraints (verified by tests):
  * No JavaScript. The static report is printable and email-friendly.
  * No external resources — no <link>, no <script>, no fonts. Email
    clients strip those anyway, and the HTML must be a single
    attachment.
  * Inline SVG only. The live viewer uses Leaflet; this static
    counterpart hand-rolls SVG and projects lat/lon to pixel space
    locally.
  * Stay under 200 KB. Practical hard limit so it fits comfortably in
    Gmail's "show original" without forcing a download.
  * No emoji.
"""

from __future__ import annotations

import html
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reuse the analysis helpers from the live viewer for correctness +
# regression-testability — same numbers in the static report and the
# live dashboard.
from sim.web.analysis import (
    bounding_box_km2,
    haversine_m,
    path_length_m,
    read_jsonl,
    read_manifest,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# ---------------------------------------------------------------------------
# Map projection: equirectangular at the AOR centroid. Good enough for a
# 1 km square at 39 deg N — the great-circle distortion is well under a
# pixel at the report's resolution.
# ---------------------------------------------------------------------------

MAP_W = 720
MAP_H = 540
MAP_PAD = 30  # pixels of breathing room around the geofence

# Fusion-gate plot dimensions.
PLOT_W = 720
PLOT_H = 220
PLOT_PAD_LEFT = 50
PLOT_PAD_RIGHT = 20
PLOT_PAD_TOP = 20
PLOT_PAD_BOT = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _project(
    lat: float,
    lon: float,
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    width: int,
    height: int,
    pad: int,
) -> tuple[float, float]:
    """Equirectangular lat/lon -> SVG pixel space.

    Y is flipped so north is up. Latitudes are scaled to a true-aspect
    rectangle: we compute the lon-span at the lat-mid, divide by the
    lat-span, and use that ratio to choose how much of the output
    rectangle each axis gets, so the SVG isn't visually stretched.
    """
    if lat_max <= lat_min or lon_max <= lon_min:
        return (width / 2.0, height / 2.0)

    inner_w = width - 2 * pad
    inner_h = height - 2 * pad

    lat_mid = (lat_min + lat_max) / 2.0
    width_m = haversine_m(lat_mid, lon_min, lat_mid, lon_max)
    height_m = haversine_m(lat_min, 0.0, lat_max, 0.0)
    if width_m <= 0 or height_m <= 0:
        return (width / 2.0, height / 2.0)

    aspect = width_m / height_m
    box_aspect = inner_w / inner_h
    if aspect >= box_aspect:
        # Limited by width.
        draw_w = inner_w
        draw_h = inner_w / aspect
    else:
        draw_h = inner_h
        draw_w = inner_h * aspect
    off_x = pad + (inner_w - draw_w) / 2.0
    off_y = pad + (inner_h - draw_h) / 2.0

    fx = (lon - lon_min) / (lon_max - lon_min)
    fy = (lat - lat_min) / (lat_max - lat_min)
    return (off_x + fx * draw_w, off_y + (1.0 - fy) * draw_h)


def _bounds_for_paths(*paths: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Merged lat/lon bbox over any number of point sequences."""
    lats: list[float] = []
    lons: list[float] = []
    for path in paths:
        for lat, lon in path:
            lats.append(lat)
            lons.append(lon)
    if not lats:
        # Sensible fallback so the SVG still renders.
        return (38.90, 38.92, -107.01, -106.99)
    return (min(lats), max(lats), min(lons), max(lons))


def _polyline_points(
    coords: list[tuple[float, float]],
    bbox: tuple[float, float, float, float],
    *,
    width: int = MAP_W,
    height: int = MAP_H,
    pad: int = MAP_PAD,
) -> str:
    lat_min, lat_max, lon_min, lon_max = bbox
    pts = [
        _project(
            lat,
            lon,
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
            width=width,
            height=height,
            pad=pad,
        )
        for lat, lon in coords
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


# ---------------------------------------------------------------------------
# Flight-data loading
# ---------------------------------------------------------------------------


def _flight_log_rows(flight_dir: Path) -> list[dict[str, Any]]:
    """Single-drone uses flight_log.jsonl; swarm uses drones.jsonl.

    For the swarm case we keep all drones interleaved — the renderer
    plots each drone's path on the same map.
    """
    fl = flight_dir / "flight_log.jsonl"
    if fl.exists():
        return read_jsonl(fl)
    dr = flight_dir / "drones.jsonl"
    if dr.exists():
        return read_jsonl(dr)
    return []


def _signal_rows(flight_dir: Path) -> list[dict[str, Any]]:
    sigs = read_jsonl(flight_dir / "signals.jsonl")
    consensus = read_jsonl(flight_dir / "consensus.jsonl")
    # Tag consensus rows so the table can flag them.
    for c in consensus:
        c.setdefault("_is_consensus", True)
    return sigs + consensus


def _ts_seconds(row: dict[str, Any]) -> float | None:
    """Best-effort timestamp -> seconds-since-epoch float."""
    ts = row.get("ts_iso") or row.get("ts") or row.get("timestamp")
    if not ts:
        # Sim-time fallback.
        st = row.get("sim_time_s")
        return float(st) if isinstance(st, (int, float)) else None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Fusion-gate analytics. We deliberately re-derive the open/approach
# counts here instead of importing summarize() from sim.web.analysis,
# because the live analysis assumes gate_state is a dict (the fixture
# format) and the actual recorder writes gate_state as a string with
# rgb_score / thermal_delta_c at the row root.
# ---------------------------------------------------------------------------


def _gate_open(row: dict[str, Any]) -> bool:
    gs = row.get("gate_state")
    if isinstance(gs, dict):
        return bool(gs.get("open", False))
    if isinstance(gs, str):
        return gs == "open"
    return False


def _gate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "open_rate": 0.0,
            "approaches": 0,
            "hits": 0,
            "hit_rate": 0.0,
            "max_rgb_score": 0.0,
            "max_thermal_delta_c": 0.0,
        }
    approaches = 0
    hits = 0
    in_approach = False
    in_hit_window = False
    open_count = 0
    max_rgb = 0.0
    max_thermal = 0.0
    for r in rows:
        rgb = float(r.get("rgb_score", 0.0) or 0.0)
        therm = float(r.get("thermal_delta_c", 0.0) or 0.0)
        max_rgb = max(max_rgb, rgb)
        max_thermal = max(max_thermal, therm)
        is_open = _gate_open(r)
        if is_open:
            open_count += 1
        candidate = rgb > 0.4 or therm > 3.0
        if candidate and not in_approach:
            in_approach = True
            approaches += 1
            in_hit_window = False
        if not candidate and in_approach:
            in_approach = False
        if in_approach and is_open and not in_hit_window:
            in_hit_window = True
            hits += 1
    return {
        "open_rate": round(open_count / len(rows), 4),
        "approaches": approaches,
        "hits": hits,
        "hit_rate": round(hits / approaches, 3) if approaches else 0.0,
        "max_rgb_score": round(max_rgb, 3),
        "max_thermal_delta_c": round(max_thermal, 2),
    }


def _stats(flight_dir: Path) -> dict[str, Any]:
    """Compute the at-a-glance statistics we display in the report."""
    manifest = read_manifest(flight_dir / "manifest.json")
    log = _flight_log_rows(flight_dir)
    signals = _signal_rows(flight_dir)
    consensus = [s for s in signals if s.get("_is_consensus")]

    # Per-drone path: in the single case there's exactly one drone_id;
    # in the swarm case drones.jsonl rows carry a drone_id.
    paths_by_drone: dict[str, list[tuple[float, float]]] = {}
    for r in log:
        lat = r.get("lat")
        lon = r.get("lon")
        if lat is None or lon is None:
            continue
        did = r.get("drone_id") or "wfw-sim01"
        paths_by_drone.setdefault(did, []).append((float(lat), float(lon)))

    total_path_m = sum(path_length_m(p) for p in paths_by_drone.values())
    all_points = [pt for path in paths_by_drone.values() for pt in path]
    area_km2 = bounding_box_km2(all_points)

    # Battery: rolled up over the first drone we see (or the only one).
    drone_ids = list(paths_by_drone.keys())
    battery_consumed_pct = 0.0
    max_alt = 0.0
    speeds: list[float] = []
    if drone_ids:
        first_drone_rows = [r for r in log if (r.get("drone_id") or drone_ids[0]) == drone_ids[0]]
        if first_drone_rows:
            b_start = first_drone_rows[0].get("battery_pct")
            b_end = first_drone_rows[-1].get("battery_pct")
            if isinstance(b_start, (int, float)) and isinstance(b_end, (int, float)):
                battery_consumed_pct = round(b_start - b_end, 1)
        max_alt = max(
            (float(r.get("alt_agl_m", 0.0) or 0.0) for r in log),
            default=0.0,
        )
        speeds = [float(r.get("speed_mps", 0.0) or 0.0) for r in log]

    by_type = Counter(s.get("signal_type", "unknown") for s in signals)
    by_action = Counter(s.get("recommended_action", "unknown") for s in signals)
    max_risk = max((float(s.get("risk_score", 0.0) or 0.0) for s in signals), default=0.0)

    duration_s = manifest.get("duration_s") or manifest.get("sim_seconds") or 0.0

    return {
        "manifest": manifest,
        "duration_s": float(duration_s),
        "drones": drone_ids,
        "n_drones": len(drone_ids),
        "row_count": len(log),
        "paths_by_drone": paths_by_drone,
        "all_points": all_points,
        "path_length_km": round(total_path_m / 1000.0, 3),
        "area_km2": round(area_km2, 3),
        "battery_consumed_pct": battery_consumed_pct,
        "max_alt_agl_m": round(max_alt, 1),
        "mean_speed_mps": round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
        "signals_total": len(signals),
        "signals_raw": len(signals) - len(consensus),
        "signals_consensus": len(consensus),
        "signals_by_type": dict(by_type),
        "signals_by_action": dict(by_action),
        "max_risk_score": round(max_risk, 1),
        "gate": _gate_metrics(log),
        "signals": signals,
    }


# ---------------------------------------------------------------------------
# SVG builders
# ---------------------------------------------------------------------------


_DRONE_PATH_COLORS = ["#4fc3f7", "#ffb300", "#66bb6a", "#ce93d8", "#ef5350"]
_SIGNAL_COLOR = {
    "smoke": "#9da7b3",
    "fire": "#ef5350",
    "thermal_anomaly": "#ff9800",
    "wildlife": "#66bb6a",
    "anomaly": "#ce93d8",
    "system_event": "#90a4ae",
}


def _signal_color(t: str) -> str:
    return _SIGNAL_COLOR.get(t, "#90a4ae")


def _build_map_svg(stats: dict[str, Any]) -> str:
    manifest = stats["manifest"]
    waypoints = manifest.get("waypoints", []) or []
    geofence = manifest.get("geofence_polygon", []) or []

    # Build the merged bbox over geofence, planned waypoints, and all
    # flown paths so everything fits.
    bbox_paths = [stats["all_points"]]
    if geofence:
        bbox_paths.append([(float(lat), float(lon)) for lat, lon in geofence])
    if waypoints:
        bbox_paths.append([
            (float(wp["lat"]), float(wp["lon"]))
            for wp in waypoints
            if "lat" in wp and "lon" in wp
        ])
    bbox = _bounds_for_paths(*bbox_paths)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {MAP_W} {MAP_H}" '
        f'class="wfw-map" role="img" '
        f'aria-label="AOR map with planned waypoints, flown paths, '
        f'and emitted signals">'
    )
    # Background.
    parts.append(
        f'<rect x="0" y="0" width="{MAP_W}" height="{MAP_H}" '
        f'fill="#0e1620" stroke="#22303d" stroke-width="1"/>'
    )

    # Subtle grid (8 columns, 6 rows).
    for i in range(1, 8):
        x = i * (MAP_W / 8.0)
        parts.append(
            f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{MAP_H}" '
            f'stroke="#1a2632" stroke-width="0.5"/>'
        )
    for i in range(1, 6):
        y = i * (MAP_H / 6.0)
        parts.append(
            f'<line x1="0" y1="{y:.1f}" x2="{MAP_W}" y2="{y:.1f}" '
            f'stroke="#1a2632" stroke-width="0.5"/>'
        )

    # Geofence polygon.
    if geofence:
        gf_pts = [(float(lat), float(lon)) for lat, lon in geofence]
        pts_attr = _polyline_points(gf_pts, bbox)
        parts.append(
            f'<polygon points="{pts_attr}" fill="#4fc3f7" '
            f'fill-opacity="0.08" stroke="#4fc3f7" stroke-width="1.5"/>'
        )

    # Planned waypoint path.
    if waypoints:
        wp_pts = [
            (float(wp["lat"]), float(wp["lon"]))
            for wp in waypoints
            if "lat" in wp and "lon" in wp
        ]
        if wp_pts:
            pts_attr = _polyline_points(wp_pts, bbox)
            parts.append(
                f'<polyline points="{pts_attr}" fill="none" '
                f'stroke="#7c8ea3" stroke-width="1.5" stroke-dasharray="4 4"/>'
            )
            for idx, (lat, lon) in enumerate(wp_pts):
                cx, cy = _project(
                    lat, lon,
                    lat_min=bbox[0], lat_max=bbox[1],
                    lon_min=bbox[2], lon_max=bbox[3],
                    width=MAP_W, height=MAP_H, pad=MAP_PAD,
                )
                parts.append(
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" '
                    f'fill="#0e1620" stroke="#7c8ea3" stroke-width="1.5"/>'
                )
                parts.append(
                    f'<text x="{cx + 6:.1f}" y="{cy - 6:.1f}" '
                    f'fill="#7c8ea3" font-size="10">WP{idx + 1}</text>'
                )

    # Flown paths, one per drone, color-coded.
    for i, (drone_id, path) in enumerate(stats["paths_by_drone"].items()):
        if not path:
            continue
        color = _DRONE_PATH_COLORS[i % len(_DRONE_PATH_COLORS)]
        # Subsample for compactness — at 10 Hz a 5-minute flight is 3000
        # points; we don't need every one in the SVG.
        step = max(1, len(path) // 800)
        sampled = path[::step]
        pts_attr = _polyline_points(sampled, bbox)
        parts.append(
            f'<polyline points="{pts_attr}" fill="none" '
            f'stroke="{color}" stroke-width="1.4" stroke-opacity="0.85"/>'
        )

    # Home marker.
    home = manifest.get("home")
    if isinstance(home, dict) and "lat" in home and "lon" in home:
        cx, cy = _project(
            float(home["lat"]), float(home["lon"]),
            lat_min=bbox[0], lat_max=bbox[1],
            lon_min=bbox[2], lon_max=bbox[3],
            width=MAP_W, height=MAP_H, pad=MAP_PAD,
        )
        parts.append(
            f'<rect x="{cx - 4:.1f}" y="{cy - 4:.1f}" width="8" height="8" '
            f'fill="#ffb300" stroke="#0e1620" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{cx + 6:.1f}" y="{cy + 4:.1f}" fill="#ffb300" '
            f'font-size="10">HOME</text>'
        )

    # Signal markers.
    for s in stats["signals"]:
        coords = s.get("coords") or {}
        lat = coords.get("lat")
        lon = coords.get("lon")
        if lat is None or lon is None:
            continue
        cx, cy = _project(
            float(lat), float(lon),
            lat_min=bbox[0], lat_max=bbox[1],
            lon_min=bbox[2], lon_max=bbox[3],
            width=MAP_W, height=MAP_H, pad=MAP_PAD,
        )
        color = _signal_color(s.get("signal_type", "anomaly"))
        is_consensus = bool(s.get("_is_consensus"))
        r = 7.0 if is_consensus else 4.0
        sw = 2.0 if is_consensus else 1.0
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{color}" fill-opacity="0.5" stroke="{color}" '
            f'stroke-width="{sw}"/>'
        )

    # Scale bar (very rough, ~200 m).
    bbox_lat_mid = (bbox[0] + bbox[1]) / 2.0
    width_m = haversine_m(bbox_lat_mid, bbox[2], bbox_lat_mid, bbox[3])
    if width_m > 0:
        # Pixels per meter at the projection.
        # Take the actual draw_w out of _project's logic by reprojecting
        # the bbox extremes.
        x_l, _ = _project(
            bbox_lat_mid, bbox[2],
            lat_min=bbox[0], lat_max=bbox[1],
            lon_min=bbox[2], lon_max=bbox[3],
            width=MAP_W, height=MAP_H, pad=MAP_PAD,
        )
        x_r, _ = _project(
            bbox_lat_mid, bbox[3],
            lat_min=bbox[0], lat_max=bbox[1],
            lon_min=bbox[2], lon_max=bbox[3],
            width=MAP_W, height=MAP_H, pad=MAP_PAD,
        )
        px_per_m = (x_r - x_l) / width_m if width_m > 0 else 0.0
        bar_m = 200.0
        bar_px = bar_m * px_per_m
        if bar_px > 20:
            bx = MAP_W - MAP_PAD - bar_px - 10
            by = MAP_H - MAP_PAD
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_px:.1f}" '
                f'height="3" fill="#cfd8dc"/>'
            )
            parts.append(
                f'<text x="{bx:.1f}" y="{by - 4:.1f}" fill="#cfd8dc" '
                f'font-size="10">200 m</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


def _build_gate_plot_svg(flight_dir: Path) -> str:
    """Time-series SVG of the fusion gate inputs.

    Three traces normalized to a shared y-axis [0, 1]:
      * rgb_score — already in [0, 1]
      * thermal_delta_c — divided by 25 so a 25 deg C delta = 1.0
      * persistence — a 1.0 line whenever gate_state == "open"

    Single-drone uses the flight_log directly. Swarm: we average across
    drones at each tick so the plot is one trace per metric (the report
    is intended for a non-engineer reader, not a deep-debug dashboard).
    """
    log = _flight_log_rows(flight_dir)
    if not log:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {PLOT_W} {PLOT_H}" class="wfw-plot">'
            f'<rect x="0" y="0" width="{PLOT_W}" height="{PLOT_H}" '
            f'fill="#0e1620"/>'
            f'<text x="{PLOT_W / 2:.0f}" y="{PLOT_H / 2:.0f}" '
            f'fill="#7c8ea3" font-size="12" text-anchor="middle">'
            f'no flight log rows</text>'
            f'</svg>'
        )

    # Bucket by sim_time_s so the swarm renders cleanly. Single-drone
    # reduces to one row per bucket trivially.
    buckets: dict[float, list[dict[str, Any]]] = {}
    for r in log:
        st = r.get("sim_time_s")
        if not isinstance(st, (int, float)):
            continue
        bucket = round(float(st), 1)
        buckets.setdefault(bucket, []).append(r)
    times = sorted(buckets.keys())
    if not times:
        times = [0.0, 1.0]
        buckets = {0.0: [{}], 1.0: [{}]}

    rgb_series: list[tuple[float, float]] = []
    thermal_series: list[tuple[float, float]] = []
    open_series: list[tuple[float, float]] = []
    for t in times:
        rows = buckets[t]
        rgbs = [float(r.get("rgb_score", 0.0) or 0.0) for r in rows]
        therms = [float(r.get("thermal_delta_c", 0.0) or 0.0) for r in rows]
        opens = [_gate_open(r) for r in rows]
        rgb_avg = sum(rgbs) / len(rgbs) if rgbs else 0.0
        therm_avg = sum(therms) / len(therms) if therms else 0.0
        open_any = any(opens)
        rgb_series.append((t, max(0.0, min(1.0, rgb_avg))))
        thermal_series.append((t, max(0.0, min(1.0, therm_avg / 25.0))))
        open_series.append((t, 1.0 if open_any else 0.0))

    t_min, t_max = times[0], times[-1]
    if t_max <= t_min:
        t_max = t_min + 1.0
    plot_w = PLOT_W - PLOT_PAD_LEFT - PLOT_PAD_RIGHT
    plot_h = PLOT_H - PLOT_PAD_TOP - PLOT_PAD_BOT

    def to_xy(series: list[tuple[float, float]]) -> str:
        out = []
        for t, v in series:
            x = PLOT_PAD_LEFT + (t - t_min) / (t_max - t_min) * plot_w
            y = PLOT_PAD_TOP + (1.0 - v) * plot_h
            out.append(f"{x:.1f},{y:.1f}")
        return " ".join(out)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {PLOT_W} {PLOT_H}" class="wfw-plot" role="img" '
        f'aria-label="Fusion gate inputs over flight time">'
    )
    parts.append(
        f'<rect x="0" y="0" width="{PLOT_W}" height="{PLOT_H}" '
        f'fill="#0e1620" stroke="#22303d" stroke-width="1"/>'
    )

    # Y axis gridlines at 0, 0.25, 0.5, 0.75, 1.
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = PLOT_PAD_TOP + (1.0 - v) * plot_h
        parts.append(
            f'<line x1="{PLOT_PAD_LEFT}" y1="{y:.1f}" '
            f'x2="{PLOT_W - PLOT_PAD_RIGHT}" y2="{y:.1f}" '
            f'stroke="#1a2632" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{PLOT_PAD_LEFT - 6:.0f}" y="{y + 3:.1f}" '
            f'fill="#7c8ea3" font-size="10" text-anchor="end">{v:.2f}</text>'
        )

    # X-axis labels (start, mid, end) in sim seconds.
    for t in (t_min, (t_min + t_max) / 2.0, t_max):
        x = PLOT_PAD_LEFT + (t - t_min) / (t_max - t_min) * plot_w
        parts.append(
            f'<text x="{x:.1f}" y="{PLOT_H - 8:.0f}" fill="#7c8ea3" '
            f'font-size="10" text-anchor="middle">{t:.0f}s</text>'
        )

    # Gate-open shaded band along the bottom (visual cue that the gate
    # was firing).
    open_segments: list[tuple[float, float]] = []
    seg_start: float | None = None
    for t, v in open_series:
        if v > 0.5 and seg_start is None:
            seg_start = t
        elif v <= 0.5 and seg_start is not None:
            open_segments.append((seg_start, t))
            seg_start = None
    if seg_start is not None:
        open_segments.append((seg_start, t_max))
    for s_start, s_end in open_segments:
        x0 = PLOT_PAD_LEFT + (s_start - t_min) / (t_max - t_min) * plot_w
        x1 = PLOT_PAD_LEFT + (s_end - t_min) / (t_max - t_min) * plot_w
        if x1 - x0 < 1.0:
            x1 = x0 + 1.0
        parts.append(
            f'<rect x="{x0:.1f}" y="{PLOT_PAD_TOP:.0f}" '
            f'width="{x1 - x0:.1f}" height="{plot_h:.1f}" '
            f'fill="#ef5350" fill-opacity="0.08"/>'
        )

    # Traces.
    parts.append(
        f'<polyline points="{to_xy(rgb_series)}" fill="none" '
        f'stroke="#4fc3f7" stroke-width="1.4"/>'
    )
    parts.append(
        f'<polyline points="{to_xy(thermal_series)}" fill="none" '
        f'stroke="#ff9800" stroke-width="1.4"/>'
    )

    # Legend.
    legend_y = PLOT_PAD_TOP + 4
    parts.append(
        f'<rect x="{PLOT_W - PLOT_PAD_RIGHT - 200:.0f}" y="{legend_y:.0f}" '
        f'width="190" height="46" fill="#0e1620" fill-opacity="0.7" '
        f'stroke="#22303d" stroke-width="0.5"/>'
    )
    parts.append(
        f'<rect x="{PLOT_W - PLOT_PAD_RIGHT - 192:.0f}" y="{legend_y + 6:.0f}" '
        f'width="10" height="2" fill="#4fc3f7"/>'
    )
    parts.append(
        f'<text x="{PLOT_W - PLOT_PAD_RIGHT - 178:.0f}" y="{legend_y + 9:.0f}" '
        f'fill="#cfd8dc" font-size="10">rgb_score</text>'
    )
    parts.append(
        f'<rect x="{PLOT_W - PLOT_PAD_RIGHT - 192:.0f}" y="{legend_y + 18:.0f}" '
        f'width="10" height="2" fill="#ff9800"/>'
    )
    parts.append(
        f'<text x="{PLOT_W - PLOT_PAD_RIGHT - 178:.0f}" y="{legend_y + 21:.0f}" '
        f'fill="#cfd8dc" font-size="10">thermal_delta_c / 25</text>'
    )
    parts.append(
        f'<rect x="{PLOT_W - PLOT_PAD_RIGHT - 192:.0f}" y="{legend_y + 30:.0f}" '
        f'width="10" height="6" fill="#ef5350" fill-opacity="0.3"/>'
    )
    parts.append(
        f'<text x="{PLOT_W - PLOT_PAD_RIGHT - 178:.0f}" y="{legend_y + 35:.0f}" '
        f'fill="#cfd8dc" font-size="10">gate open</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def _build_signal_table(stats: dict[str, Any], *, max_rows: int = 30) -> str:
    """HTML table of emitted signals.

    Truncates at ``max_rows`` to keep the report under the 200 KB cap
    even when a flight emits hundreds of raw single-drone signals.
    Consensus rows are always shown first.
    """
    signals = list(stats["signals"])
    signals.sort(key=lambda s: (not s.get("_is_consensus"), s.get("timestamp", "")))
    rows = signals[:max_rows]

    parts: list[str] = []
    parts.append('<table class="wfw-table">')
    parts.append(
        "<thead><tr>"
        "<th>#</th>"
        "<th>timestamp</th>"
        "<th>kind</th>"
        "<th>type</th>"
        "<th>conf</th>"
        "<th>risk</th>"
        "<th>action</th>"
        "<th>drone</th>"
        "</tr></thead>"
    )
    parts.append("<tbody>")
    for i, s in enumerate(rows, start=1):
        is_consensus = bool(s.get("_is_consensus"))
        ts = html.escape(str(s.get("timestamp", "")))
        sig_type = html.escape(str(s.get("signal_type", "?")))
        conf = float(s.get("confidence", 0.0) or 0.0)
        risk = float(s.get("risk_score", 0.0) or 0.0)
        action = html.escape(str(s.get("recommended_action", "?")))
        drone = html.escape(str(s.get("drone_id", "?")))
        kind = "consensus" if is_consensus else "raw"
        row_class = "consensus" if is_consensus else ""
        parts.append(
            f'<tr class="{row_class}">'
            f"<td>{i}</td>"
            f"<td>{ts}</td>"
            f"<td>{kind}</td>"
            f"<td><span class=\"chip\" "
            f"style=\"background:{_signal_color(s.get('signal_type', ''))}\">"
            f"{sig_type}</span></td>"
            f"<td>{conf:.2f}</td>"
            f"<td>{risk:.0f}</td>"
            f"<td>{action}</td>"
            f"<td>{drone}</td>"
            "</tr>"
        )
    if len(signals) > len(rows):
        parts.append(
            f'<tr><td colspan="8" class="more">'
            f"and {len(signals) - len(rows)} more signal(s) in "
            f"signals.jsonl + consensus.jsonl"
            "</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Top-level renderer
# ---------------------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f} s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _stat_card(label: str, value: str, hint: str = "") -> str:
    hint_html = f'<div class="hint">{html.escape(hint)}</div>' if hint else ""
    return (
        f'<div class="card">'
        f'<div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div>'
        f"{hint_html}"
        f"</div>"
    )


def _render_html(stats: dict[str, Any], flight_dir: Path) -> str:
    css = _read_text(TEMPLATES_DIR / "styles.css")
    drone_icon = _read_text(TEMPLATES_DIR / "icons" / "drone.svg")

    manifest = stats["manifest"]
    is_swarm = manifest.get("kind") == "swarm" or "drones.jsonl" in (
        manifest.get("outputs", {}) or {}
    ).keys()
    title_run = "swarm" if is_swarm else "single-drone"
    mission_name = manifest.get("mission_name") or manifest.get("mission") or flight_dir.name
    scenario_name = (
        manifest.get("scenario_name") or manifest.get("scenario") or "(scenario)"
    )

    cards: list[str] = []
    cards.append(_stat_card("flight type", title_run))
    cards.append(
        _stat_card("duration", _format_duration(stats["duration_s"]), "sim time")
    )
    cards.append(_stat_card("path", f'{stats["path_length_km"]:.2f} km'))
    cards.append(
        _stat_card("AOR bbox", f'{stats["area_km2"]:.3f} km²', "bounding-box upper bound")
    )
    cards.append(_stat_card("signals (total)", str(stats["signals_total"])))
    if stats["signals_consensus"]:
        cards.append(
            _stat_card(
                "signals (consensus)",
                str(stats["signals_consensus"]),
                f"{stats['signals_raw']} raw + "
                f"{stats['signals_consensus']} confirmed",
            )
        )
    else:
        cards.append(_stat_card("max risk score", f'{stats["max_risk_score"]:.0f}'))
    cards.append(
        _stat_card(
            "fusion gate",
            f'{stats["gate"]["hits"]}/{stats["gate"]["approaches"]} hits',
            f'open-rate {stats["gate"]["open_rate"]:.2%}',
        )
    )
    cards.append(
        _stat_card(
            "battery",
            f'{stats["battery_consumed_pct"]:.1f}%',
            f'max alt {stats["max_alt_agl_m"]:.0f} m AGL',
        )
    )

    # Signals-by-type chart (small bar chart inline as SVG).
    chips_html: list[str] = []
    by_type = stats["signals_by_type"]
    if by_type:
        total = sum(by_type.values())
        for t, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
            color = _signal_color(t)
            pct = (n / total * 100.0) if total else 0.0
            chips_html.append(
                f'<div class="byrow">'
                f'<div class="bytag"><span class="dot" '
                f'style="background:{color}"></span>'
                f'{html.escape(t)}</div>'
                f'<div class="bybar"><span class="byfill" '
                f'style="width:{pct:.1f}%; background:{color}"></span></div>'
                f'<div class="bynum">{n}</div>'
                f"</div>"
            )

    map_svg = _build_map_svg(stats)
    plot_svg = _build_gate_plot_svg(flight_dir)
    table_html = _build_signal_table(stats)

    description = manifest.get("scenario_description") or ""
    description_html = (
        f'<p class="desc">{html.escape(description.strip())}</p>'
        if description
        else ""
    )

    swarm_extra = ""
    if is_swarm:
        per_drone = manifest.get("per_drone_signals", {})
        per_drone_rows = "".join(
            f"<tr><td>{html.escape(str(d))}</td><td>{n}</td></tr>"
            for d, n in per_drone.items()
        )
        swarm_extra = (
            '<section><h2>swarm parameters</h2>'
            '<table class="wfw-table compact">'
            f'<tr><th>n_drones</th><td>{manifest.get("n_drones", "?")}</td></tr>'
            f'<tr><th>k_consensus</th><td>{manifest.get("k_consensus", "?")}</td></tr>'
            f'<tr><th>r_spatial_m</th><td>{manifest.get("r_spatial_m", "?")}</td></tr>'
            f'<tr><th>t_window_s</th><td>{manifest.get("t_window_s", "?")}</td></tr>'
            f'<tr><th>loss_rate</th><td>{manifest.get("loss_rate", "?")}</td></tr>'
            "</table>"
            "<h3>signals per drone</h3>"
            '<table class="wfw-table compact">'
            "<thead><tr><th>drone_id</th><th>signals</th></tr></thead>"
            f"<tbody>{per_drone_rows}</tbody></table>"
            "</section>"
        )

    seed = manifest.get("seed", "?")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wildfire-watch demo report — {html.escape(str(mission_name))}</title>
<style>{css}</style>
</head>
<body>
<header class="hero">
  <div class="hero-icon">{drone_icon}</div>
  <div class="hero-text">
    <div class="eyebrow">wildfire-watch demo report</div>
    <h1>{html.escape(str(mission_name))}</h1>
    <p class="sub">scenario: <code>{html.escape(str(scenario_name))}</code> &middot;
       seed: <code>{html.escape(str(seed))}</code> &middot;
       flight type: <code>{html.escape(title_run)}</code></p>
    {description_html}
  </div>
</header>

<section>
  <h2>at a glance</h2>
  <div class="cards">{"".join(cards)}</div>
</section>

<section>
  <h2>area of operations</h2>
  <p class="muted">Planned waypoints (dashed), flown drone path
  (solid colored line per drone), and emitted signals (filled circles —
  larger ring on consensus-confirmed events). Geofence shown as the
  light-blue polygon. North is up.</p>
  {map_svg}
</section>

<section>
  <h2>fusion gate over time</h2>
  <p class="muted">Live RGB and thermal evidence feeding the gate at
  10 Hz. Red bands mark the windows where the gate was open and a
  signal was emittable. The thermal trace is normalized to a 25 deg C
  delta so both axes share the [0, 1] range; the raw values are in
  flight_log.jsonl.</p>
  {plot_svg}
</section>

<section>
  <h2>signals by type</h2>
  <div class="bytype">{"".join(chips_html) or "<em>no signals emitted</em>"}</div>
</section>

<section>
  <h2>emitted signals</h2>
  {table_html}
</section>

{swarm_extra}

<section>
  <h2>how to read this report</h2>
  <p>This is a recorded run of the wildfire-watch flight simulator
  against the canonical <a href="https://en.wikipedia.org/wiki/Slate_River_(Colorado)">Slate River</a>
  patrol mission near Crested Butte, Colorado — the AOR documented in
  the repo's <code>AOR.md</code>. Every number above is derived directly
  from the flight directory's <code>manifest.json</code>,
  <code>flight_log.jsonl</code>, and <code>signals.jsonl</code>; no
  numbers are mocked.</p>
  <p>The <strong>fusion gate</strong> is the multimodal trigger that
  decides when an observation becomes a signal. It listens to the RGB
  detector, the thermal delta, and how long both have persisted — only
  when all three line up does it open and ship a wildfire_signal v1
  record downstream. The static plot above shows the inputs; the red
  bands show where the gate fired.</p>
  <p>The <strong>signal table</strong> is the operator-facing output.
  Each row is a wildfire_signal v1 record: schema-validated,
  drone-attributable, geo-tagged, and ready to forward to ATAK / Apollo
  / Lattice via the TAK CoT bridge in
  <code>sapphire_integration/tak/</code>. Consensus rows mean two or
  more drones independently saw the same plume within the spatial /
  temporal windows.</p>
  <p>The full live viewer (with Leaflet basemap, time scrubbing, and
  Server-Sent-Events replay) lives at <code>sim/web/server.py</code>;
  this static report is the printable, email-friendly counterpart.</p>
</section>

<footer>
  <p>Generated <code>{html.escape(_now_iso())}</code> from
  <code>{html.escape(flight_dir.name)}</code>.
  AOR: Gunnison Valley + Crested Butte corridor, Gunnison County,
  Colorado. West Elk Wilderness is hard no-fly per 36 CFR 261.16.</p>
  <p>Repo: <code>github.com/arigatoexpress/wildfire-watch</code>.
  Source code Apache-2.0; report content (text, derived numbers) is
  CC-BY-4.0. No third-party imagery is embedded in this file.</p>
</footer>
</body>
</html>
"""


def render_report(flight_dir: os.PathLike | str, output_html: os.PathLike | str) -> None:
    """Render a single self-contained HTML file from a flight dir.

    The output is a static, printable, email-friendly HTML document. It
    contains an inline SVG map of the AOR with the planned path + flown
    paths, an inline SVG plot of the fusion gate inputs over time, a
    table of emitted signals with timestamps + types + risk scores, and
    a "how to read this" section for non-technical readers.

    No JavaScript, no external CSS, no external fonts, no
    network-dependent images. The HTML is one file you can email,
    embed in a README via plain link, or host at a static URL.
    """
    flight_dir = Path(flight_dir).expanduser().resolve()
    output_html = Path(output_html).expanduser()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    if not flight_dir.is_dir():
        raise FileNotFoundError(f"flight dir not found: {flight_dir}")
    if not (flight_dir / "manifest.json").exists():
        raise FileNotFoundError(
            f"flight dir missing manifest.json: {flight_dir}"
        )

    stats = _stats(flight_dir)
    html_text = _render_html(stats, flight_dir)
    output_html.write_text(html_text, encoding="utf-8")
