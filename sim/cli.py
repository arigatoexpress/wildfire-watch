"""Simulator CLI.

    python -m sim.cli run <mission.yaml> --scenario <name|path>
                          [--speed-multiplier 5]
                          [--pipe-to-sapphire]
                          [--out ~/wildfire-watch-flights/]
                          [--seed 0]
                          [--drone-id wfw-sim01]
                          [--max-sim-seconds 3600]

`--scenario` accepts either a bare scenario name (resolved against
sim/scenarios/<name>.yaml) or a path to a scenario YAML.

`--pipe-to-sapphire` shells out to
~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py for each emitted
signal, mirroring ml/fire_detection/demo.py.

`--speed-multiplier` lets a 30-min flight finish in ~6 minutes for fast
iteration. Internal sim-time stays accurate; only the wall-clock pacing
between ticks is divided by the multiplier.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import airframe as airframe_module
from .mission import load_mission
from .recorder import Recorder
from .runner import RunnerConfig, SimulationRunner
from .scenario import ScenarioEngine, load_scenario

logger = logging.getLogger("sim.cli")

DEFAULT_OUT = Path.home() / "wildfire-watch-flights"
SAPPHIRE_BRIDGE = (
    Path.home()
    / "Code"
    / "Sapphire"
    / "plugins"
    / "claw-sapphire"
    / "tools"
    / "wildfire.py"
)


def _resolve_scenario_path(name_or_path: str) -> Path:
    p = Path(name_or_path).expanduser()
    if p.exists():
        return p
    here = Path(__file__).resolve().parent
    candidate = here / "scenarios" / f"{name_or_path}.yaml"
    if candidate.exists():
        return candidate
    candidate = here / "scenarios" / name_or_path
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"scenario '{name_or_path}' not found as a path or under sim/scenarios/"
    )


def _pipe_to_sapphire(signal: dict[str, Any]) -> dict[str, Any]:
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


def _build_run_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("run", help="Run a mission against a scenario.")
    p.add_argument("mission", help="Path to a mission YAML file.")
    p.add_argument(
        "--scenario",
        required=True,
        help="Scenario name (resolves to sim/scenarios/<name>.yaml) or YAML path.",
    )
    p.add_argument(
        "--speed-multiplier",
        type=float,
        default=0.0,
        help="Wall-clock pacing multiplier. 0 (default) = run as fast as possible.",
    )
    p.add_argument("--pipe-to-sapphire", action="store_true",
                   help="Forward each emitted signal to the Sapphire bridge.")
    p.add_argument("--out", default=str(DEFAULT_OUT),
                   help=f"Output root directory (default: {DEFAULT_OUT}).")
    p.add_argument("--seed", type=int, default=0,
                   help="Deterministic seed (forwarded to RunnerConfig).")
    p.add_argument("--drone-id", default="wfw-sim01",
                   help="Drone ID embedded in every wildfire_signal.")
    p.add_argument("--tick-hz", type=float, default=10.0,
                   help="Simulator tick rate (default 10 Hz).")
    p.add_argument("--max-sim-seconds", type=float, default=3600.0,
                   help="Hard cap on simulated flight time (default 3600 s).")
    return p


def _build_info_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("info", help="Print metadata about a mission file.")
    p.add_argument("mission", help="Path to a mission YAML file.")
    return p


def _build_airframes_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    return sub.add_parser("airframes", help="List known airframe profiles.")


def _cmd_run(args: argparse.Namespace) -> int:
    mission = load_mission(args.mission)
    scenario_path = _resolve_scenario_path(args.scenario)
    scenario = load_scenario(scenario_path)
    engine = ScenarioEngine(scenario)
    config = RunnerConfig(
        drone_id=args.drone_id,
        tick_hz=args.tick_hz,
        seed=args.seed,
        speed_multiplier=args.speed_multiplier,
        return_to_home=mission.return_to_home,
    )

    sapphire_pipe = args.pipe_to_sapphire

    with Recorder(args.out, scenario.name) as recorder:
        def on_signal(sig: dict[str, Any]) -> None:
            recorder.on_signal(sig)
            if sapphire_pipe:
                resp = _pipe_to_sapphire(sig)
                sys.stderr.write(
                    f"[sapphire] signal_id={sig.get('signal_id')} "
                    f"ok={resp.get('ok', False)}\n"
                )

        last_real_emit = time.monotonic()

        def on_tick(rec) -> None:
            recorder.on_tick(rec)
            # Optional wall-clock pacing for live demos.
            nonlocal last_real_emit
            if args.speed_multiplier and args.speed_multiplier > 0:
                target_dt = (1.0 / args.tick_hz) / args.speed_multiplier
                now = time.monotonic()
                sleep = target_dt - (now - last_real_emit)
                if sleep > 0:
                    time.sleep(sleep)
                last_real_emit = time.monotonic()

        runner = SimulationRunner(
            mission=mission,
            scenario_engine=engine,
            config=config,
            on_signal=on_signal,
            on_tick=on_tick,
        )
        result = runner.run(max_sim_seconds=args.max_sim_seconds)

        manifest = {
            "mission": mission.name,
            "zone_id": mission.zone_id,
            "scenario": scenario.name,
            "scenario_description": scenario.description,
            "airframe": mission.airframe_name,
            "drone_id": args.drone_id,
            "tick_hz": args.tick_hz,
            "seed": args.seed,
            "ticks": result.ticks,
            "sim_seconds": round(result.sim_seconds, 3),
            "signals_emitted": result.signals_emitted,
            "waypoints_reached": result.waypoints_reached,
            "final_battery_pct": round(result.final_battery_pct, 2),
            "outputs": {
                "flight_log": str(recorder.flight_log_path),
                "srt": str(recorder.srt_path),
                "signals": str(recorder.signals_path),
            },
        }
        recorder.close(manifest)

    sys.stdout.write(json.dumps(manifest, indent=2) + "\n")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    mission = load_mission(args.mission)
    info = {
        "name": mission.name,
        "zone_id": mission.zone_id,
        "airframe": mission.airframe_name,
        "waypoints": len(mission.waypoints),
        "total_ground_distance_m": round(mission.total_ground_distance_m(), 1),
        "estimated_flight_time_s": round(mission.estimated_flight_time_s(), 1),
        "battery_budget_ok": mission.battery_budget_ok(),
    }
    sys.stdout.write(json.dumps(info, indent=2) + "\n")
    return 0


def _cmd_airframes(_args: argparse.Namespace) -> int:
    for name in airframe_module.all_names():
        prof = airframe_module.get(name)
        sys.stdout.write(
            f"{prof.name:18s} cruise={prof.cruise_speed_mps} m/s, "
            f"max={prof.max_horizontal_speed_mps} m/s, "
            f"battery={prof.battery_minutes} min, "
            f"ceiling={prof.service_ceiling_agl_m} m AGL\n"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m sim.cli",
        description="wildfire-watch kinematic flight simulator.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    _build_run_parser(sub)
    _build_info_parser(sub)
    _build_airframes_parser(sub)

    args = parser.parse_args(argv)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "info":
        return _cmd_info(args)
    if args.cmd == "airframes":
        return _cmd_airframes(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
