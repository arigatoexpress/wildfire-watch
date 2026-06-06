#!/usr/bin/env python3
"""Turn a FIREFIGHT match log into schema-valid wildfire_signals.

The browser game (game/game3d.js) exports a per-tick ``*__drones.jsonl`` in the
real wildfire-watch flight-log shape, including the simulated onboard
perception readings ``rgb_score`` and ``thermal_delta_c``. This post-processor
replays that log through the CANONICAL fusion gate and signal builder —
``ml.fire_detection.infer.should_emit()`` and ``ml.fire_detection.infer.build_signal()``
— exactly as ``mavic_post_flight.py`` does. It does not reimplement either; it
composes against them, per the project rule.

The result is a ``*__signals.jsonl`` that drops straight into
``wildfire-watch-flights/`` and the Sapphire ``signal_logger`` ingest path.

Usage:
    python3 game/firefight_to_signals.py FIREFIGHT3D-<stamp>_human_vs_ai__drones.jsonl
    python3 game/firefight_to_signals.py <log.jsonl> --zone-id slate-river-drainage --threshold 0.65
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Make the repo root importable when run as a plain script from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.fire_detection.infer import build_signal, should_emit  # noqa: E402


def _recommended_action(risk: float, confidence: float, auto_loiter: float) -> str:
    """Map composite risk to the schema's recommended_action enum."""
    if risk >= 85:
        return "notify_fire_dept"
    if confidence >= auto_loiter:
        return "loiter_and_capture"
    if risk >= 45:
        return "notify_operator"
    return "log_only"


def convert(
    log_path: Path,
    *,
    zone_id: str,
    threshold: float,
    persistence_min: int,
    auto_loiter: float,
    out_path: Path | None,
) -> Path:
    frames = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # Per-drone persistence + episode hysteresis so we emit one signal per
    # sustained detection rather than one per tick parked over a fire.
    streak: dict[str, int] = {}
    emitted_in_episode: dict[str, bool] = {}
    signals: list[dict] = []

    for f in frames:
        did = f["drone_id"]
        rgb = float(f.get("rgb_score", 0.0))
        thermal = float(f.get("thermal_delta_c", 0.0))
        gate_inputs = dict(
            rgb_score=rgb,
            thermal_delta_c=thermal,
            geofence_ok=True,        # game keeps every drone inside the zone
            wind_consistent=True,    # steady ambient wind in-match
            threshold=threshold,
            persistence_min=persistence_min,
        )
        hot = rgb >= threshold and thermal >= 5.0
        streak[did] = streak.get(did, 0) + 1 if hot else 0
        if not hot:
            emitted_in_episode[did] = False
            continue

        if should_emit(persistence_frames=streak[did], **gate_inputs) and not emitted_in_episode.get(did):
            emitted_in_episode[did] = True
            confidence = round(min(1.0, rgb), 3)
            risk = round(min(100.0, confidence * 70 + (15 if thermal >= 20 else 0) + 10), 1)
            coords = {
                "lat": f["lat"], "lon": f["lon"],
                "alt_agl_m": f.get("alt_agl_m", 80.0),
                "alt_msl_m": f.get("alt_msl_m"),
                "heading_deg": f.get("heading_deg", 0.0),
                "ground_speed_mps": f.get("speed_mps", 0.0),
            }
            uri = (
                f"gs://wildfire-watch-evidence/{zone_id}/"
                f"{f.get('ts_iso', '')[:10]}/{did}/frame_000.jpg"
            )
            # Estimated target = the fire under the drone's sensor footprint.
            # (A real fielded build would geolocate the plume; here the drone
            # is suppressing right over it, so drone coords are a fair proxy.)
            target = {
                "lat": f["lat"], "lon": f["lon"], "alt_msl_m": f.get("alt_msl_m"),
                "estimation_method": "visual_geolocation",
                "horizontal_uncertainty_m": 30.0,
            }
            sig = build_signal(
                drone_id=did,
                zone_id=zone_id,
                coords=coords,
                target_coords=target,
                signal_type="fire",          # rgb + thermal positive => fire
                confidence=confidence,
                rgb_yolo_score=round(rgb, 3),
                thermal_delta_c=round(thermal, 1),
                frame_uris=[uri],
                risk_score=risk,
                recommended_action=_recommended_action(risk, confidence, auto_loiter),
            )
            # Stamp the game's own timestamp instead of wall-clock now().
            if f.get("ts_iso"):
                sig["timestamp"] = f["ts_iso"]
            signals.append(sig)

    out = out_path or log_path.with_name(log_path.name.replace("__drones.jsonl", "__signals.jsonl"))
    if out == log_path:
        out = log_path.with_suffix(".signals.jsonl")
    out.write_text("".join(json.dumps(s) + "\n" for s in signals), encoding="utf-8")

    by_drone = Counter(s["drone_id"] for s in signals)
    by_action = Counter(s["recommended_action"] for s in signals)
    print(f"frames read:        {len(frames)}")
    print(f"signals emitted:    {len(signals)}  (gate threshold={threshold}, persistence>={persistence_min})")
    print(f"  per drone:        {dict(by_drone)}")
    print(f"  per action:       {dict(by_action)}")
    print(f"wrote:              {out}")

    # Optional: validate against the canonical schema if jsonschema is present.
    try:
        import jsonschema  # noqa: PLC0415

        schema = json.loads(
            (_REPO_ROOT / "sapphire_integration" / "wildfire_signal_schema.json").read_text()
        )
        for s in signals:
            jsonschema.validate(s, schema)
        print(f"schema validation:  all {len(signals)} signals valid against v1.0.0")
    except ModuleNotFoundError:
        print("schema validation:  skipped (pip install jsonschema to enable)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("log", type=Path, help="FIREFIGHT *__drones.jsonl match log")
    p.add_argument("--zone-id", default="slate-river-drainage")
    p.add_argument("--threshold", type=float, default=0.65, help="RGB fusion-gate threshold")
    p.add_argument("--persistence", type=int, default=5, help="min consecutive hot frames")
    p.add_argument("--auto-loiter", type=float, default=0.85)
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    if not a.log.exists():
        p.error(f"log not found: {a.log}")
    convert(
        a.log,
        zone_id=a.zone_id,
        threshold=a.threshold,
        persistence_min=a.persistence,
        auto_loiter=a.auto_loiter,
        out_path=a.out,
    )


if __name__ == "__main__":
    main()
