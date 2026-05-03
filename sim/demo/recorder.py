# Copyright 2026 wildfire-watch contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# See the LICENSE file in the repo root for the full text.
"""Canonical demo-flight recorder.

Drives the existing single-drone simulator + the swarm runner against a
fixed mission + scenario + seed. Both runs are written under
``output_dir/{single,swarm}/`` so :func:`sim.demo.renderer.render_report`
can render either independently and ``cli all`` can render whichever the
operator pointed at.

This module does NOT reach into ``sim.cli`` / ``sim.swarm.cli`` (those
parse argv); it composes :class:`sim.runner.SimulationRunner` and
:class:`sim.swarm.runner.SwarmRunner` directly and reuses the existing
recorders. Same code paths the CLIs use, just no argparse layer.

Determinism: with a fixed (mission, scenario, seed, tick_hz) tuple the
underlying simulator is deterministic per its own contract — every
``signal_id`` is built by ``infer.build_signal()`` from the sim_time +
zone + drone_id, so re-running with the same seed produces identical
signal ids. We surface that contract here as ``record_canonical_flight``
being idempotent on its inputs.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# These imports are intentionally module-level — they're cheap and the
# whole point of this module is to drive the simulator.
from sim.mission import load_mission
from sim.recorder import Recorder
from sim.runner import RunnerConfig, SimulationRunner
from sim.scenario import ScenarioEngine, load_scenario
from sim.swarm.comms import CommsConfig
from sim.swarm.recorder import SwarmRecorder
from sim.swarm.runner import SwarmRunner, SwarmRunnerConfig

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The canonical demo is pinned to the Slate River mission + the smoke
# plume scenarios documented in AOR.md. If those file paths move, this
# is the one place to update.
CANONICAL_MISSION = REPO_ROOT / "sim" / "missions" / "gunnison_slate_river_1km2.yaml"
CANONICAL_SINGLE_SCENARIO = REPO_ROOT / "sim" / "scenarios" / "single_smoke_plume.yaml"
CANONICAL_SWARM_SCENARIO = (
    REPO_ROOT / "sim" / "swarm" / "scenarios" / "consensus_smoke.yaml"
)

# Hard caps so re-running the demo doesn't accidentally turn into a
# multi-hour soak. A full Slate River patrol with seed 42 + the smoke
# plume scenario emits ~80 raw signals and lands inside ~830 sim seconds
# at 10 Hz; the swarm consensus run is shorter (~450 s).
SINGLE_MAX_SIM_SECONDS = 1800.0
SWARM_MAX_SIM_SECONDS = 600.0
DEFAULT_SEED = 42
DEFAULT_TICK_HZ = 10.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wipe_dir(d: Path) -> None:
    """Idempotency helper: remove the directory if it exists."""
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Soft-fail so a corrupt line doesn't kill the manifest.
                continue
    return out


def _record_single(
    *,
    output_dir: Path,
    seed: int,
    tick_hz: float,
    drone_id: str,
) -> dict[str, Any]:
    """Run one canonical single-drone flight into ``output_dir``.

    The output dir is wiped first so re-invocation is idempotent: there
    will be exactly one ``SIM-*_single_smoke_plume`` subdirectory after
    we return.
    """
    _wipe_dir(output_dir)

    mission = load_mission(str(CANONICAL_MISSION))
    scenario = load_scenario(CANONICAL_SINGLE_SCENARIO)
    engine = ScenarioEngine(scenario)
    config = RunnerConfig(
        drone_id=drone_id,
        tick_hz=tick_hz,
        seed=seed,
        speed_multiplier=0.0,
        return_to_home=mission.return_to_home,
    )

    with Recorder(output_dir, scenario.name) as recorder:
        def on_signal(sig: dict[str, Any]) -> None:
            recorder.on_signal(sig)

        def on_tick(rec) -> None:
            recorder.on_tick(rec)

        runner = SimulationRunner(
            mission=mission,
            scenario_engine=engine,
            config=config,
            on_signal=on_signal,
            on_tick=on_tick,
        )
        result = runner.run(max_sim_seconds=SINGLE_MAX_SIM_SECONDS)

        manifest = {
            "kind": "single",
            "mission": mission.name,
            "mission_name": mission.name,
            "zone_id": mission.zone_id,
            "scenario": scenario.name,
            "scenario_name": scenario.name,
            "scenario_description": scenario.description,
            "airframe": mission.airframe_name,
            "drone_id": drone_id,
            "tick_hz": tick_hz,
            "seed": seed,
            "ticks": result.ticks,
            "sim_seconds": round(result.sim_seconds, 3),
            "signals_emitted": result.signals_emitted,
            "waypoints_reached": result.waypoints_reached,
            "final_battery_pct": round(result.final_battery_pct, 2),
            "started_at": _now_iso(),
            "ended_at": _now_iso(),
            "duration_s": round(result.sim_seconds, 3),
            "geofence_polygon": [list(p) for p in mission.geofence_polygon],
            "waypoints": [
                {
                    "index": i,
                    "lat": wp.lat,
                    "lon": wp.lon,
                    "alt_agl_m": wp.alt_agl_m,
                    "label": f"WP{i + 1}",
                }
                for i, wp in enumerate(mission.waypoints)
            ],
            "home": {
                "lat": mission.home.lat,
                "lon": mission.home.lon,
                "alt_msl_m": mission.home.alt_msl_m,
            },
            "outputs": {
                "flight_log": str(recorder.flight_log_path.relative_to(output_dir)),
                "srt": str(recorder.srt_path.relative_to(output_dir)),
                "signals": str(recorder.signals_path.relative_to(output_dir)),
            },
        }
        recorder.close(manifest)
        return manifest


def _record_swarm(
    *,
    output_dir: Path,
    seed: int,
    tick_hz: float,
    n_drones: int,
    k_consensus: int,
) -> dict[str, Any]:
    """Run one canonical swarm flight into ``output_dir``."""
    _wipe_dir(output_dir)

    mission = load_mission(str(CANONICAL_MISSION))
    scenario = load_scenario(CANONICAL_SWARM_SCENARIO)
    comms_cfg = CommsConfig(loss_rate=0.05, seed=seed)
    config = SwarmRunnerConfig(
        n_drones=n_drones,
        k_consensus=k_consensus,
        r_spatial_m=75.0,
        t_window_s=60.0,
        tick_hz=tick_hz,
        seed=seed,
        speed_multiplier=0.0,
        comms_config=comms_cfg,
    )

    with SwarmRecorder(output_dir, scenario.name) as recorder:
        def on_drone_tick(rec) -> None:
            recorder.on_drone_tick(rec)

        def on_raw_signal(emitter_id: str, sig: dict[str, Any]) -> None:
            recorder.on_signal(emitter_drone_id=emitter_id, signal=sig)

        def on_consensus(sig: dict[str, Any]) -> None:
            recorder.on_consensus(sig)

        def on_comms(entries) -> None:
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
        result = runner.run(max_sim_seconds=SWARM_MAX_SIM_SECONDS)

        manifest = {
            "kind": "swarm",
            "mission": mission.name,
            "mission_name": mission.name,
            "zone_id": mission.zone_id,
            "scenario": scenario.name,
            "scenario_name": scenario.name,
            "scenario_description": scenario.description,
            "n_drones": n_drones,
            "k_consensus": k_consensus,
            "r_spatial_m": 75.0,
            "t_window_s": 60.0,
            "tick_hz": tick_hz,
            "seed": seed,
            "loss_rate": 0.05,
            "ticks": result.ticks,
            "sim_seconds": round(result.sim_seconds, 3),
            "raw_signals": result.raw_signals,
            "consensus_signals": result.consensus_signals,
            "drones_dead_battery": result.drones_dead_battery,
            "per_drone_signals": result.per_drone_signals,
            "started_at": _now_iso(),
            "ended_at": _now_iso(),
            "duration_s": round(result.sim_seconds, 3),
            "geofence_polygon": [list(p) for p in mission.geofence_polygon],
            "waypoints": [
                {
                    "index": i,
                    "lat": wp.lat,
                    "lon": wp.lon,
                    "alt_agl_m": wp.alt_agl_m,
                    "label": f"WP{i + 1}",
                }
                for i, wp in enumerate(mission.waypoints)
            ],
            "home": {
                "lat": mission.home.lat,
                "lon": mission.home.lon,
                "alt_msl_m": mission.home.alt_msl_m,
            },
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
                "drones": str(recorder.drones_path.relative_to(output_dir)),
                "signals": str(recorder.signals_path.relative_to(output_dir)),
                "consensus": str(recorder.consensus_path.relative_to(output_dir)),
                "comms": str(recorder.comms_path.relative_to(output_dir)),
            },
        }
        recorder.close(manifest)
        return manifest


def record_canonical_flight(
    *,
    seed: int = DEFAULT_SEED,
    output_dir: os.PathLike | str,
    tick_hz: float = DEFAULT_TICK_HZ,
    drone_id: str = "wfw-sim01",
    n_drones: int = 3,
    k_consensus: int = 2,
) -> dict[str, Any]:
    """Record the canonical wildfire-watch demo flight.

    Runs both a single-drone Mavic-profile patrol and a 3-drone
    consensus swarm against ``sim/missions/gunnison_slate_river_1km2.yaml``
    + the canonical smoke-plume scenarios, with the seed pinned for
    reproducibility.

    Output layout under ``output_dir``::

        output_dir/
            single/SIM-<ts>_single_smoke_plume/
                manifest.json + flight_log.jsonl + signals.jsonl + flight.srt
            swarm/SWARM-<ts>_consensus_smoke/
                manifest.json + drones.jsonl + signals.jsonl
                + consensus.jsonl + comms.jsonl
            manifest.json    -- top-level, points at both runs

    Returns a manifest dict (also written to ``output_dir/manifest.json``)
    with timestamps, seed, mission/scenario URIs, signal counts, output
    paths, and a sample CoT XML snippet for one signal.

    Idempotent on (seed, mission, scenario): the single + swarm output
    dirs are wiped before each call. With seed=42 + the canonical
    scenario, the same set of signal_ids comes out every time the
    underlying ``infer.build_signal()`` is fed the same inputs.
    """
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    single_dir = output_dir / "single"
    swarm_dir = output_dir / "swarm"

    started_at = _now_iso()

    single_manifest = _record_single(
        output_dir=single_dir,
        seed=seed,
        tick_hz=tick_hz,
        drone_id=drone_id,
    )
    swarm_manifest = _record_swarm(
        output_dir=swarm_dir,
        seed=seed,
        tick_hz=tick_hz,
        n_drones=n_drones,
        k_consensus=k_consensus,
    )

    # Sample CoT XML for the first emitted signal, if any. Lazy-import
    # so the recorder has zero hard dep on the TAK module.
    sample_cot_xml: str | None = None
    sample_signal_id: str | None = None
    sample_source: str | None = None
    swarm_run_dir = next(swarm_dir.glob("SWARM-*_consensus_smoke"), None)
    if swarm_run_dir is not None:
        consensus_path = swarm_run_dir / "consensus.jsonl"
        sigs = _read_jsonl(consensus_path)
        if sigs:
            sample_signal_id = sigs[0].get("signal_id")
            sample_source = "swarm/consensus"
            try:
                from sapphire_integration.tak.cot_event import (  # noqa: PLC0415
                    build_cot_event,
                )
                sample_cot_xml = build_cot_event(sigs[0])
            except Exception:  # noqa: BLE001
                sample_cot_xml = None

    if sample_cot_xml is None:
        single_run_dir = next(single_dir.glob("SIM-*_single_smoke_plume"), None)
        if single_run_dir is not None:
            sigs = _read_jsonl(single_run_dir / "signals.jsonl")
            if sigs:
                sample_signal_id = sigs[0].get("signal_id")
                sample_source = "single/raw"
                try:
                    from sapphire_integration.tak.cot_event import (  # noqa: PLC0415
                        build_cot_event,
                    )
                    sample_cot_xml = build_cot_event(sigs[0])
                except Exception:  # noqa: BLE001
                    sample_cot_xml = None

    top_manifest = {
        "kind": "canonical_demo",
        "started_at": started_at,
        "ended_at": _now_iso(),
        "seed": seed,
        "tick_hz": tick_hz,
        "mission_yaml_uri": str(CANONICAL_MISSION.relative_to(REPO_ROOT)),
        "single_scenario_yaml_uri": str(
            CANONICAL_SINGLE_SCENARIO.relative_to(REPO_ROOT)
        ),
        "swarm_scenario_yaml_uri": str(
            CANONICAL_SWARM_SCENARIO.relative_to(REPO_ROOT)
        ),
        "scenarios": ["single_smoke_plume", "consensus_smoke"],
        "single": {
            "output_dir": str(single_dir.relative_to(output_dir)),
            "signals_emitted": single_manifest.get("signals_emitted", 0),
            "ticks": single_manifest.get("ticks", 0),
            "sim_seconds": single_manifest.get("sim_seconds", 0.0),
        },
        "swarm": {
            "output_dir": str(swarm_dir.relative_to(output_dir)),
            "raw_signals": swarm_manifest.get("raw_signals", 0),
            "consensus_signals": swarm_manifest.get("consensus_signals", 0),
            "ticks": swarm_manifest.get("ticks", 0),
            "sim_seconds": swarm_manifest.get("sim_seconds", 0.0),
            "n_drones": swarm_manifest.get("n_drones", 0),
            "k_consensus": swarm_manifest.get("k_consensus", 0),
        },
        "sample_cot": {
            "signal_id": sample_signal_id,
            "source": sample_source,
            "xml": sample_cot_xml,
        },
    }
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(top_manifest, f, indent=2, default=str)
    return top_manifest
