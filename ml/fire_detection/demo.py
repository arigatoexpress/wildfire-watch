"""wildfire-watch — synthetic-replay demo.

Runs the end-to-end signal pipeline against a scripted scenario: a smoke
plume builds for 6 frames in a target zone, the multimodal fusion gate
fires, and a wildfire_signal v1.0.0 is constructed and printed (or
piped into the Sapphire wildfire plugin tool).

This lets you exercise the whole path on a laptop with no hardware:

    # Local dry-run, signals printed to stdout
    python3 ml/fire_detection/demo.py

    # Pipe each emitted signal into the Sapphire bridge
    python3 ml/fire_detection/demo.py --pipe-to-sapphire

When piping, each signal becomes one ingest call against
~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py and is appended
to ~/Code/Sapphire/data/wildfire_signals.jsonl with a
`wildfire.signal.detected` event_bus envelope.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from infer import build_signal, should_emit  # noqa: E402

SAPPHIRE_BRIDGE = (
    Path.home()
    / "Code"
    / "Sapphire"
    / "plugins"
    / "claw-sapphire"
    / "tools"
    / "wildfire.py"
)


# Scripted scenario: 8 frames over a target zone. RGB score climbs as smoke
# becomes visible, thermal lags a frame, persistence requirement met at frame 5.
SCRIPT = [
    # (rgb_score, thermal_delta_c, lat, lon, alt_agl_m)
    (0.10, 0.5, 36.4906, -121.1825, 80.0),
    (0.30, 1.2, 36.4906, -121.1825, 80.0),
    (0.55, 3.4, 36.4906, -121.1825, 80.0),
    (0.72, 7.1, 36.4906, -121.1826, 80.0),
    (0.84, 11.8, 36.4906, -121.1826, 80.0),
    (0.91, 16.2, 36.4906, -121.1827, 80.0),  # gate triggers here
    (0.93, 18.5, 36.4906, -121.1827, 80.0),
    (0.95, 21.4, 36.4906, -121.1827, 80.0),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch synthetic-replay demo.")
    p.add_argument("--drone_id", default="wfw-demo01")
    p.add_argument("--zone_id", default="monterey-pinnacles-east")
    p.add_argument("--confidence_threshold", type=float, default=0.65)
    p.add_argument("--auto_loiter_threshold", type=float, default=0.85)
    p.add_argument("--persistence_frames", type=int, default=5)
    p.add_argument(
        "--pipe-to-sapphire",
        action="store_true",
        help="Send every emitted signal through plugins/claw-sapphire/tools/wildfire.py.",
    )
    return p.parse_args()


def pipe_to_sapphire_bridge(signal: dict) -> dict:
    """Invoke the Sapphire wildfire bridge with `action=ingest`."""
    if not SAPPHIRE_BRIDGE.exists():
        return {"ok": False, "error": f"bridge not found: {SAPPHIRE_BRIDGE}"}
    payload = json.dumps({"action": "ingest", "signal": signal})
    proc = subprocess.run(
        ["python3", str(SAPPHIRE_BRIDGE)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "stderr": proc.stderr.strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "raw": proc.stdout}


def main() -> int:
    args = parse_args()
    persistence: deque[bool] = deque(maxlen=args.persistence_frames)
    emit_count = 0

    for idx, (rgb, thermal, lat, lon, alt) in enumerate(SCRIPT, start=1):
        persistence.append(rgb >= args.confidence_threshold)
        run_length = sum(persistence)
        coords = {"lat": lat, "lon": lon, "alt_agl_m": alt}

        gate_open = should_emit(
            rgb_score=rgb,
            thermal_delta_c=thermal,
            persistence_frames=run_length,
            geofence_ok=True,
            wind_consistent=True,
            threshold=args.confidence_threshold,
            persistence_min=args.persistence_frames,
        )
        sys.stderr.write(
            f"[frame {idx}] rgb={rgb:.2f} thermal_delta={thermal:.1f}C "
            f"persistence={run_length}/{args.persistence_frames} gate={'OPEN' if gate_open else 'closed'}\n"
        )
        if not gate_open:
            continue

        confidence = min(1.0, 0.5 * rgb + 0.5 * min(thermal / 30.0, 1.0))
        signal_type = "fire" if thermal >= 15.0 else "smoke"
        recommended = (
            "loiter_and_capture"
            if confidence >= args.auto_loiter_threshold
            else "notify_operator"
        )
        signal = build_signal(
            drone_id=args.drone_id,
            zone_id=args.zone_id,
            coords=coords,
            target_coords=None,
            signal_type=signal_type,
            confidence=confidence,
            rgb_yolo_score=rgb,
            thermal_delta_c=thermal,
            frame_uris=[
                f"file:///tmp/wildfire-watch-demo/{args.zone_id}/frame_{idx:03d}.jpg"
            ],
            risk_score=confidence * 100.0,
            recommended_action=recommended,
        )

        emit_count += 1
        if args.pipe_to_sapphire:
            response = pipe_to_sapphire_bridge(signal)
            sys.stdout.write(json.dumps({"emit": signal, "bridge": response}) + "\n")
        else:
            sys.stdout.write(json.dumps(signal) + "\n")

    sys.stderr.write(f"\nemitted {emit_count} signals over {len(SCRIPT)} frames\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
