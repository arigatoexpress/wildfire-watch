"""End-to-end tests for sim.swarm.runner.SwarmRunner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sim.mission import load_mission
from sim.scenario import load_scenario
from sim.swarm.comms import CommsConfig
from sim.swarm.recorder import SwarmRecorder
from sim.swarm.runner import SwarmRunner, SwarmRunnerConfig


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GUNNISON_MISSION = REPO_ROOT / "sim" / "missions" / "gunnison_slate_river_1km2.yaml"
SWARM_SCENARIOS = REPO_ROOT / "sim" / "swarm" / "scenarios"


def _load(scenario_name: str):
    mission = load_mission(GUNNISON_MISSION)
    scenario = load_scenario(SWARM_SCENARIOS / f"{scenario_name}.yaml")
    return mission, scenario


def test_three_drone_clean_patrol_emits_no_consensus(tmp_path):
    mission, scenario = _load("three_drone_patrol")
    cfg = SwarmRunnerConfig(
        n_drones=3,
        k_consensus=2,
        tick_hz=10.0,
        seed=0,
        comms_config=CommsConfig(loss_rate=0.0, seed=0),
        start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
    )

    consensus_signals: list[dict] = []
    raw_signals: list[tuple[str, dict]] = []
    runner = SwarmRunner(
        mission=mission,
        scenario=scenario,
        config=cfg,
        on_consensus=lambda s: consensus_signals.append(s),
        on_raw_signal=lambda did, s: raw_signals.append((did, s)),
    )
    result = runner.run(max_sim_seconds=30.0)
    assert result.consensus_signals == 0
    assert len(consensus_signals) == 0
    assert len(raw_signals) == 0


def test_consensus_smoke_fires_kof3(tmp_path):
    mission, scenario = _load("consensus_smoke")
    cfg = SwarmRunnerConfig(
        n_drones=3,
        k_consensus=2,  # k-of-3, but we want consensus to fire
        tick_hz=10.0,
        seed=0,
        comms_config=CommsConfig(loss_rate=0.0, seed=0),
        start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
    )

    consensus_signals: list[dict] = []
    runner = SwarmRunner(
        mission=mission,
        scenario=scenario,
        config=cfg,
        on_consensus=lambda s: consensus_signals.append(s),
    )
    result = runner.run(max_sim_seconds=30.0)
    assert result.consensus_signals >= 1, (
        f"expected consensus to fire; raw signals={result.raw_signals}, "
        f"per_drone={result.per_drone_signals}"
    )
    sig = consensus_signals[0]
    assert sig["signal_subtype"] == "sim/consensus_confirmed"
    # Recommended action should be escalated. Single-drone emits at
    # notify_operator -> notify_fire_dept; at loiter_and_capture
    # (high-confidence) -> auto_dispatch_response.
    assert sig["recommended_action"] in (
        "notify_fire_dept",
        "auto_dispatch_response",
    )
    assert "consensus" in sig
    assert sig["consensus"]["peer_confirmations"] >= 2


def test_single_witness_anomaly_does_not_fire(tmp_path):
    mission, scenario = _load("single_witness_anomaly")
    cfg = SwarmRunnerConfig(
        n_drones=3,
        k_consensus=2,
        tick_hz=10.0,
        seed=0,
        comms_config=CommsConfig(loss_rate=0.0, seed=0),
        start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
    )
    runner = SwarmRunner(
        mission=mission,
        scenario=scenario,
        config=cfg,
    )
    result = runner.run(max_sim_seconds=30.0)
    assert result.consensus_signals == 0


def test_recorder_writes_all_four_files(tmp_path):
    mission, scenario = _load("consensus_smoke")
    cfg = SwarmRunnerConfig(
        n_drones=3,
        k_consensus=2,
        tick_hz=10.0,
        seed=0,
        comms_config=CommsConfig(loss_rate=0.0, seed=0),
        start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with SwarmRecorder(tmp_path, "consensus_smoke", run_id="SWARM-TEST") as rec:
        runner = SwarmRunner(
            mission=mission,
            scenario=scenario,
            config=cfg,
            on_drone_tick=rec.on_drone_tick,
            on_raw_signal=lambda did, s: rec.on_signal(emitter_drone_id=did, signal=s),
            on_consensus=rec.on_consensus,
            on_comms=rec.on_comms_entries,
        )
        result = runner.run(max_sim_seconds=30.0)
        rec.close({"raw": result.raw_signals, "consensus": result.consensus_signals})

    out_dir = tmp_path / "SWARM-TEST_consensus_smoke"
    assert (out_dir / "drones.jsonl").exists()
    assert (out_dir / "signals.jsonl").exists()
    assert (out_dir / "consensus.jsonl").exists()
    assert (out_dir / "comms.jsonl").exists()
    assert (out_dir / "manifest.json").exists()

    # consensus.jsonl should have at least one row.
    lines = (out_dir / "consensus.jsonl").read_text().strip().splitlines()
    assert len(lines) >= 1
    parsed = json.loads(lines[0])
    assert parsed["signal_subtype"] == "sim/consensus_confirmed"


def test_full_comms_loss_blocks_consensus(tmp_path):
    """With loss_rate=1.0, peers never receive each other's signals.
    Self-votes from each drone will fire ONE separate cluster per drone,
    but no cluster will reach k=2 because no drone hears another."""
    mission, scenario = _load("consensus_smoke")
    cfg = SwarmRunnerConfig(
        n_drones=3,
        k_consensus=2,
        tick_hz=10.0,
        seed=0,
        comms_config=CommsConfig(loss_rate=1.0, seed=0),
        start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
    )
    runner = SwarmRunner(
        mission=mission,
        scenario=scenario,
        config=cfg,
    )
    result = runner.run(max_sim_seconds=30.0)
    # All 3 drones may emit raw signals (their target_coords cluster
    # them spatially since they all see the same plume), so the voter
    # *can* form a multi-drone cluster from local self-votes alone.
    # We accept ZERO or MORE consensus emissions; the assertion that
    # matters is consensus is NOT amplified by peer comms.
    # For the specific case where each drone self-confirms its OWN emit
    # only, no k=2 can be reached.
    # Since drones are spatially separated and each computes target
    # coords from its OWN position + bearing, the targets will land in
    # different lat/lons (>> 75 m apart) and will not cluster.
    assert result.consensus_signals == 0


def test_per_drone_signal_counts_align(tmp_path):
    mission, scenario = _load("consensus_smoke")
    cfg = SwarmRunnerConfig(
        n_drones=3,
        k_consensus=2,
        tick_hz=10.0,
        seed=0,
        comms_config=CommsConfig(loss_rate=0.0, seed=0),
        start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
    )
    runner = SwarmRunner(
        mission=mission,
        scenario=scenario,
        config=cfg,
    )
    result = runner.run(max_sim_seconds=30.0)
    assert sum(result.per_drone_signals.values()) == result.raw_signals
    # All 3 drones in the consensus_smoke scenario should emit at least 1.
    for did in ("wfw-sim01", "wfw-sim02", "wfw-sim03"):
        assert result.per_drone_signals.get(did, 0) >= 1


def test_sub_zones_returned_in_result(tmp_path):
    mission, scenario = _load("three_drone_patrol")
    cfg = SwarmRunnerConfig(n_drones=3, k_consensus=2, tick_hz=10.0)
    runner = SwarmRunner(mission=mission, scenario=scenario, config=cfg)
    result = runner.run(max_sim_seconds=2.0)
    assert len(result.sub_zones) == 3
    assert {z.drone_index for z in result.sub_zones} == {0, 1, 2}
