"""Recorder — writes flight_log.jsonl + flight.srt + signals.jsonl.

Output layout (per run):

    OUTROOT/SIM-YYYY-MM-DDTHHMMSS_<scenario>/
        flight_log.jsonl   — one JSON row per tick (10 Hz default)
        flight.srt         — one cue per second, DJI-Fly compatible
        signals.jsonl      — one wildfire_signal v1 per emit
        manifest.json      — run metadata + final counts

The SRT format intentionally mirrors what
ml/fire_detection/mavic_post_flight.parse_srt already accepts: bracketed
key:value pairs with `latitude`, `longitude`, `rel_alt`, `abs_alt`, plus
a leading wallclock line. This guarantees the existing post-flight
parser can round-trip simulator output.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runner import TickRecord

logger = logging.getLogger("sim.recorder")


def _format_srt_timestamp(seconds: float) -> str:
    """SRT-format hh:mm:ss,mmm from float seconds."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000.0))
    hours = total_ms // 3_600_000
    rem = total_ms - hours * 3_600_000
    minutes = rem // 60_000
    rem -= minutes * 60_000
    secs = rem // 1000
    ms = rem - secs * 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _build_srt_block(
    cue_idx: int,
    start_s: float,
    end_s: float,
    rec: TickRecord,
) -> str:
    """Produce one DJI-Fly-compatible SRT cue.

    Format mirrors what mavic_post_flight._LAT_RE / _LON_RE / _REL_ALT_RE
    / _ABS_ALT_RE recognize, plus the wallclock line _WALLCLOCK_RE picks up.
    """
    # Strip the trailing 'Z' for a wallclock-style line; parse_srt's
    # _WALLCLOCK_RE wants `YYYY-MM-DD HH:MM:SS[.frac]`.
    wall_line = rec.ts_iso.replace("Z", "").replace("T", " ")
    return (
        f"{cue_idx}\n"
        f"{_format_srt_timestamp(start_s)} --> {_format_srt_timestamp(end_s)}\n"
        f'<font size="28">SrtCnt : {cue_idx}, DiffTime : 1000ms\n'
        f"{wall_line}\n"
        f"[iso : 100] [shutter : 1/1000.0] [fnum : 280] [ev : 0] "
        f"[latitude: {rec.lat:.6f}] [longitude: {rec.lon:.6f}] "
        f"[rel_alt: {rec.alt_agl_m:.3f} abs_alt: {rec.alt_msl_m:.3f}] </font>\n"
    )


class Recorder:
    """Writes the four output files for one simulation run."""

    def __init__(
        self,
        outroot: str | os.PathLike,
        scenario_name: str,
        *,
        run_id: str | None = None,
        srt_cue_period_s: float = 1.0,
    ):
        out = Path(outroot).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("SIM-%Y-%m-%dT%H%M%S")
        self.dir = out / f"{run_id}_{scenario_name}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.flight_log_path = self.dir / "flight_log.jsonl"
        self.srt_path = self.dir / "flight.srt"
        self.signals_path = self.dir / "signals.jsonl"
        self.manifest_path = self.dir / "manifest.json"
        self._flight_log = self.flight_log_path.open("w", encoding="utf-8")
        self._signals = self.signals_path.open("w", encoding="utf-8")
        self._srt = self.srt_path.open("w", encoding="utf-8")
        self._cue_idx = 0
        self._next_cue_at_s = 0.0
        self._srt_cue_period_s = srt_cue_period_s
        self._last_srt_record: TickRecord | None = None

    # ------------------------------------------------------------------
    # Per-event writers
    # ------------------------------------------------------------------

    def on_tick(self, rec: TickRecord) -> None:
        """Append a flight_log row + maybe an SRT cue."""
        self._flight_log.write(json.dumps(asdict(rec)) + "\n")
        if rec.sim_time_s + 1e-6 >= self._next_cue_at_s:
            self._cue_idx += 1
            start = rec.sim_time_s
            end = rec.sim_time_s + self._srt_cue_period_s
            self._srt.write(_build_srt_block(self._cue_idx, start, end, rec) + "\n")
            self._next_cue_at_s = rec.sim_time_s + self._srt_cue_period_s
        self._last_srt_record = rec

    def on_signal(self, signal: dict[str, Any]) -> None:
        self._signals.write(json.dumps(signal) + "\n")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self, manifest: dict[str, Any]) -> None:
        # Flush + close the streams.
        self._flight_log.close()
        self._signals.close()
        self._srt.close()
        with self.manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, default=str)

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Best-effort close so partial runs leave parseable files.
        for f in (self._flight_log, self._signals, self._srt):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass
