"""Swarm CLI.

    python -m sim.swarm.cli run <mission.yaml>
        --scenario <name|path>
        --drones N
        [--k K_CONSENSUS]
        [--r-spatial 75]
        [--t-window 60]
        [--speed-multiplier 5]
        [--pipe-to-sapphire]   # only CONFIRMED consensus signals piped
        [--out ~/wildfire-watch-flights]
        [--seed 0]
        [--max-sim-seconds 600]

`--pipe-to-sapphire` only forwards the CONFIRMED consensus signals (not
every raw single-drone emit). This is intentional: the bridge
downstream is meant to see *high-confidence* events, not every flicker
seen by one drone.
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

from ..mission import load_mission
from ..scenario import load_scenario
from .recorder import SwarmRecorder
from .runner import SwarmRunner, SwarmRunnerConfig

logger = logging.getLogger("sim.swarm.cli")

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
    # Fall back to the single-drone scenarios dir for backward compat.
    sister = here.parent / "scenarios" / f"{name_or_path}.yaml"
    if sister.exists():
        return sister
    raise FileNotFoundError(
        f"swarm scenario '{name_or_path}' not found in sim/swarm/scenarios/ or sim/scenarios/"
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
    p = sub.add_parser("run", help="Run a swarm mission against a scenario.")
    p.add_argument("mission", help="Path to a mission YAML file.")
    p.add_argument(
        "--scenario",
        required=True,
        help="Scenario name (resolves to sim/swarm/scenarios/<name>.yaml) or YAML path.",
    )
    p.add_argument("--drones", type=int, default=3,
                   help="Number of drones in the fleet (default 3).")
    p.add_argument("--k", type=int, default=2,
                   help="Consensus threshold k-of-N (default 2).")
    p.add_argument("--r-spatial", type=float, default=75.0,
                   help="Consensus spatial radius in meters (default 75).")
    p.add_argument("--t-window", type=float, default=60.0,
                   help="Consensus temporal window in seconds (default 60).")
    p.add_argument("--speed-multiplier", type=float, default=0.0,
                   help="Wall-clock pacing multiplier. 0 = run as fast as possible.")
    p.add_argument("--pipe-to-sapphire", action="store_true",
                   help="Forward CONFIRMED consensus signals to the Sapphire bridge.")
    p.add_argument("--out", default=str(DEFAULT_OUT),
                   help=f"Output root directory (default: {DEFAULT_OUT}).")
    p.add_argument("--seed", type=int, default=0,
                   help="Deterministic seed for the comms model.")
    p.add_argument("--tick-hz", type=float, default=10.0,
                   help="Simulator tick rate (default 10 Hz).")
    p.add_argument("--max-sim-seconds", type=float, default=600.0,
                   help="Hard cap on simulated flight time (default 600 s).")
    p.add_argument("--loss-rate", type=float, default=0.05,
                   help="Comms loss rate (default 0.05 = 5%%).")
    return p


def _cmd_run(args: argparse.Namespace) -> int:
    mission = load_mission(args.mission)
    scenario_path = _resolve_scenario_path(args.scenario)
    scenario = load_scenario(scenario_path)

    from .comms import CommsConfig
    comms_cfg = CommsConfig(loss_rate=args.loss_rate, seed=args.seed)

    config = SwarmRunnerConfig(
        n_drones=args.drones,
        k_consensus=args.k,
        r_spatial_m=args.r_spatial,
        t_window_s=args.t_window,
        tick_hz=args.tick_hz,
        seed=args.seed,
        speed_multiplier=args.speed_multiplier,
        comms_config=comms_cfg,
    )

    sapphire_pipe = args.pipe_to_sapphire

    last_real_emit = time.monotonic()

    with SwarmRecorder(args.out, scenario.name) as recorder:
        def on_drone_tick(rec):
            recorder.on_drone_tick(rec)
            nonlocal last_real_emit
            if args.speed_multiplier and args.speed_multiplier > 0:
                target_dt = (1.0 / args.tick_hz) / args.speed_multiplier
                # Fleet emits N records per tick; only pace once.
                if rec.drone_id.endswith("01"):
                    now = time.monotonic()
                    sleep = target_dt - (now - last_real_emit)
                    if sleep > 0:
                        time.sleep(sleep)
                    last_real_emit = time.monotonic()

        def on_raw_signal(emitter_id: str, sig: dict[str, Any]) -> None:
            recorder.on_signal(emitter_drone_id=emitter_id, signal=sig)

        def on_consensus(sig: dict[str, Any]) -> None:
            recorder.on_consensus(sig)
            if sapphire_pipe:
                resp = _pipe_to_sapphire(sig)
                sys.stderr.write(
                    f"[sapphire] consensus signal_id={sig.get('signal_id')} "
                    f"ok={resp.get('ok', False)}\n"
                )

        def on_comms(entries):
            recorder.on_comms_entries(entries)

        runner = SwarmRunner(
            mission=mission,
            scenario=scenario,
            config=config,
            on_drone_tick=on_drone_tick,
            on_raw_signal=on_raw_signal,
            on_consensus=on_consensus,
            on_comms=on_comms,
        )
        result = runner.run(max_sim_seconds=args.max_sim_seconds)

        manifest = {
            "mission": mission.name,
            "zone_id": mission.zone_id,
            "scenario": scenario.name,
            "scenario_description": scenario.description,
            "n_drones": args.drones,
            "k_consensus": args.k,
            "r_spatial_m": args.r_spatial,
            "t_window_s": args.t_window,
            "tick_hz": args.tick_hz,
            "seed": args.seed,
            "loss_rate": args.loss_rate,
            "ticks": result.ticks,
            "sim_seconds": round(result.sim_seconds, 3),
            "raw_signals": result.raw_signals,
            "consensus_signals": result.consensus_signals,
            "drones_dead_battery": result.drones_dead_battery,
            "per_drone_signals": result.per_drone_signals,
            "sub_zones": [
                {
                    "drone_index": z.drone_index,
                    "centroid": list(z.centroid),
                    "bbox": list(z.bbox),
                    "area_km2": round(z.area_km2(), 4),
                }
                for z in result.sub_zones
            ],
            "outputs": {
                "drones": str(recorder.drones_path),
                "signals": str(recorder.signals_path),
                "consensus": str(recorder.consensus_path),
                "comms": str(recorder.comms_path),
            },
        }
        recorder.close(manifest)

    sys.stdout.write(json.dumps(manifest, indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m sim.swarm.cli",
        description="wildfire-watch swarm flight simulator (N drones, k-of-N consensus).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    _build_run_parser(sub)
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return _cmd_run(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
