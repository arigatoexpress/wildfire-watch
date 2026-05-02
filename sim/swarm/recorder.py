"""SwarmRecorder — writes one swarm-run output directory.

Output layout:

    OUTROOT/SWARM-YYYY-MM-DDTHHMMSS_<scenario>/
        manifest.json     — mission, scenario, n_drones, k, R, T, counts
        drones.jsonl      — one row per drone per tick (multi-emitter)
        signals.jsonl     — raw single-drone wildfire_signal v1 emits
        consensus.jsonl   — CONFIRMED consensus_signal_v1 emits
        comms.jsonl       — every comms decision (delivered/dropped/partition)

This is intentionally separate from sim.recorder.Recorder — the data
shapes differ (multi-drone rows, consensus events, comms forensics). The
single-drone recorder is left untouched.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .comms import CommsLogEntry
from .fleet import DroneTickRecord


class SwarmRecorder:
    """Writes the four output files for one swarm run."""

    def __init__(
        self,
        outroot: str | os.PathLike,
        scenario_name: str,
        *,
        run_id: str | None = None,
    ):
        out = Path(outroot).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        if run_id is None:
            run_id = datetime.utcnow().strftime("SWARM-%Y-%m-%dT%H%M%S")
        self.dir = out / f"{run_id}_{scenario_name}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.drones_path = self.dir / "drones.jsonl"
        self.signals_path = self.dir / "signals.jsonl"
        self.consensus_path = self.dir / "consensus.jsonl"
        self.comms_path = self.dir / "comms.jsonl"
        self.manifest_path = self.dir / "manifest.json"

        self._drones = self.drones_path.open("w", encoding="utf-8")
        self._signals = self.signals_path.open("w", encoding="utf-8")
        self._consensus = self.consensus_path.open("w", encoding="utf-8")
        self._comms = self.comms_path.open("w", encoding="utf-8")

    # ------------------------------------------------------------------
    # Per-event writers
    # ------------------------------------------------------------------

    def on_drone_tick(self, rec: DroneTickRecord) -> None:
        self._drones.write(json.dumps(asdict(rec)) + "\n")

    def on_signal(self, *, emitter_drone_id: str, signal: dict[str, Any]) -> None:
        out = dict(signal)
        out["_emitter_drone_id"] = emitter_drone_id
        self._signals.write(json.dumps(out) + "\n")

    def on_consensus(self, signal: dict[str, Any]) -> None:
        self._consensus.write(json.dumps(signal) + "\n")

    def on_comms_entries(self, entries: list[CommsLogEntry]) -> None:
        for e in entries:
            self._comms.write(json.dumps(_dataclass_to_dict(e)) + "\n")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self, manifest: dict[str, Any]) -> None:
        for f in (self._drones, self._signals, self._consensus, self._comms):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass
        with self.manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, default=str)

    def __enter__(self) -> "SwarmRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for f in (self._drones, self._signals, self._consensus, self._comms):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"cannot serialize {type(obj).__name__}")
