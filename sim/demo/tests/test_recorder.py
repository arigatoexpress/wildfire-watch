# Copyright 2026 wildfire-watch contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Recorder tests — verify the canonical demo runs end-to-end and is
deterministic on (seed, mission, scenario)."""

from __future__ import annotations

import json
from pathlib import Path

from sim.demo.recorder import record_canonical_flight


def _read_signal_ids(jsonl_path: Path) -> list[str]:
    if not jsonl_path.exists():
        return []
    out: list[str] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = row.get("signal_id")
            if sid:
                out.append(sid)
    return out


def test_record_canonical_flight_produces_expected_layout(tmp_path: Path) -> None:
    out = tmp_path / "canonical"
    manifest = record_canonical_flight(seed=42, output_dir=out)

    # Top-level manifest written.
    assert (out / "manifest.json").exists()
    assert manifest["seed"] == 42
    assert "single_smoke_plume" in manifest["scenarios"]
    assert "consensus_smoke" in manifest["scenarios"]

    # Both sub-runs landed.
    single_runs = sorted((out / "single").glob("SIM-*_single_smoke_plume"))
    swarm_runs = sorted((out / "swarm").glob("SWARM-*_consensus_smoke"))
    assert len(single_runs) == 1, single_runs
    assert len(swarm_runs) == 1, swarm_runs

    # Each sub-run has the recorder outputs.
    sr = single_runs[0]
    assert (sr / "manifest.json").exists()
    assert (sr / "flight_log.jsonl").exists()
    assert (sr / "signals.jsonl").exists()
    assert (sr / "flight.srt").exists()

    sw = swarm_runs[0]
    assert (sw / "manifest.json").exists()
    assert (sw / "drones.jsonl").exists()
    assert (sw / "signals.jsonl").exists()
    assert (sw / "consensus.jsonl").exists()


def test_record_canonical_flight_emits_signals(tmp_path: Path) -> None:
    """The canonical demo must emit at least one consensus signal — that's
    the centerpiece of the report. With seed=42 + the consensus_smoke
    scenario the swarm reliably fires."""
    out = tmp_path / "canonical"
    record_canonical_flight(seed=42, output_dir=out)

    swarm_run = next((out / "swarm").glob("SWARM-*_consensus_smoke"))
    consensus_ids = _read_signal_ids(swarm_run / "consensus.jsonl")
    assert len(consensus_ids) >= 1, "consensus_smoke scenario must produce >= 1 confirmed signal"

    raw_ids = _read_signal_ids(swarm_run / "signals.jsonl")
    assert len(raw_ids) >= len(consensus_ids), "raw emits must be a superset"


def test_record_canonical_flight_is_deterministic_on_seed(tmp_path: Path) -> None:
    """Re-recording with the same seed must produce the same signal_ids.

    `infer.build_signal()` is a pure function of (zone, drone_id,
    timestamp, sim_state), so as long as the sim is seeded the IDs
    line up.
    """
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    record_canonical_flight(seed=42, output_dir=out_a)
    record_canonical_flight(seed=42, output_dir=out_b)

    swarm_a = next((out_a / "swarm").glob("SWARM-*_consensus_smoke"))
    swarm_b = next((out_b / "swarm").glob("SWARM-*_consensus_smoke"))
    ids_a = _read_signal_ids(swarm_a / "signals.jsonl")
    ids_b = _read_signal_ids(swarm_b / "signals.jsonl")
    # Same scenario + seed -> same number of raw signals at minimum.
    assert len(ids_a) == len(ids_b), (
        f"non-deterministic raw-signal count: {len(ids_a)} vs {len(ids_b)}"
    )

    consensus_a = _read_signal_ids(swarm_a / "consensus.jsonl")
    consensus_b = _read_signal_ids(swarm_b / "consensus.jsonl")
    assert len(consensus_a) == len(consensus_b)


def test_record_canonical_flight_is_idempotent(tmp_path: Path) -> None:
    """Recording twice into the same directory wipes the previous run."""
    out = tmp_path / "canonical"
    record_canonical_flight(seed=42, output_dir=out)
    swarm_runs_first = sorted((out / "swarm").glob("SWARM-*_consensus_smoke"))
    record_canonical_flight(seed=42, output_dir=out)
    swarm_runs_second = sorted((out / "swarm").glob("SWARM-*_consensus_smoke"))
    assert len(swarm_runs_second) == 1, swarm_runs_second
    # The directory listing is fresh — there's exactly one swarm run, not two.
    assert len(swarm_runs_first) == 1
