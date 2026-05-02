"""Mavic Mini flight-log -> GpsFix iterator.

DJI Fly does not expose a live MAVLink stream on the Mavic Mini 1/2. The
operator's only path to GPS truth post-flight is one of:

  - Embedded SRT subtitles next to each .MP4 (already handled by
    `ml/fire_detection/mavic_post_flight.py`).
  - A CSV export from the DJI Fly app, the Airdata.com web upload, or a
    DatCon-decoded .DAT file. THIS module covers the CSV path.

For Phase 0 this lets us run the full inference pipeline against a real
DJI flight: pair a video with the matching CSV, and the detector knows
where each frame was shot from.

Recognised CSV dialects (column-name match is case- and space-insensitive):

  DJI Fly       : "OSD.flyTime [s]", "OSD.latitude", "OSD.longitude",
                  "OSD.height [m]", "OSD.altitude [m]"
  Airdata       : "time(millisecond)", "latitude", "longitude",
                  "height_above_takeoff(meters)"
  DatCon /
  CsvView       : "Clock:offsetTime", "GPS:Lat", "GPS:Long",
                  "General:relativeHeight"
  Generic       : "ts", "lat", "lon", "alt_agl_m"   (used by tests + the
                  e2e harness in `tests/integration/`)

Output: a sequence of `GpsFix` named tuples sorted by `t_offset_s`. The
struct keys match what `infer.build_signal()` expects in the `coords` dict
so callers can do `coords = fix.to_coords()` directly.

This module is pure stdlib — no numpy, no pandas — so it imports clean on
the Pis and on a stock CI container.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class GpsFix:
    """One timestamped GPS sample from the flight log."""

    t_offset_s: float        # seconds since takeoff
    lat: float
    lon: float
    alt_agl_m: float         # height above takeoff
    alt_msl_m: float | None  # MSL altitude when the source supplied it

    def to_coords(self) -> dict[str, float]:
        """Shape that `infer.build_signal(coords=...)` expects."""
        c = {"lat": self.lat, "lon": self.lon, "alt_agl_m": self.alt_agl_m}
        if self.alt_msl_m is not None:
            c["alt_msl_m"] = self.alt_msl_m
        return c


# ---------------------------------------------------------------------------
# Dialect resolution
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Header normalisation: lower, strip, drop spaces and bracket suffixes.

    "OSD.height [m]" -> "osd.height"
    "GPS:Lat"        -> "gps:lat"
    "time(millisecond)" -> "time"
    """
    s = name.strip().lower()
    # Drop any "(...)" or "[...]" suffix — both are unit annotations.
    for opener, closer in (("(", ")"), ("[", "]")):
        if opener in s:
            s = s.split(opener, 1)[0].strip()
    return s.replace(" ", "")


# Dialect = ordered list of (normalised-header, role) pairs. Roles:
#   t_ms / t_s  — pick whichever timestamp column is available
#   lat / lon
#   alt_agl     — height above takeoff
#   alt_msl     — absolute MSL altitude (optional)
#
# Multiple aliases per role are checked in order; first match wins.
_DIALECTS: tuple[dict[str, tuple[str, ...]], ...] = (
    # Generic — used by tests + the e2e harness.
    {
        "t_s": ("ts", "t", "time_s", "t_offset_s"),
        "lat": ("lat", "latitude"),
        "lon": ("lon", "longitude", "long"),
        "alt_agl": ("alt_agl_m", "alt_agl", "alt"),
    },
    # DJI Fly app export.
    {
        "t_s": ("osd.flytime", "flytime"),
        "lat": ("osd.latitude",),
        "lon": ("osd.longitude",),
        "alt_agl": ("osd.height",),
        "alt_msl": ("osd.altitude",),
    },
    # Airdata.com export.
    {
        "t_ms": ("time",),
        "lat": ("latitude",),
        "lon": ("longitude",),
        "alt_agl": ("height_above_takeoff", "altitude_above_takeoff", "height"),
    },
    # DatCon / CsvView decoder export.
    {
        "t_s": ("clock:offsettime", "offsettime"),
        "lat": ("gps:lat",),
        "lon": ("gps:long", "gps:lon"),
        "alt_agl": ("general:relativeheight",),
        "alt_msl": ("general:absolutealtitude",),
    },
)


def _resolve_dialect(headers: list[str]) -> dict[str, str]:
    """Pick the first dialect whose required roles all match.

    Returns a mapping of role -> the actual header name in the file
    (NOT the normalised one) so the row-reader can index `row[name]` directly.
    """
    norm = {_normalize(h): h for h in headers}
    for dialect in _DIALECTS:
        resolved: dict[str, str] = {}
        for role, aliases in dialect.items():
            for alias in aliases:
                if alias in norm:
                    resolved[role] = norm[alias]
                    break
        # Required roles for any flight log: a timestamp, lat, lon, and AGL.
        has_time = "t_s" in resolved or "t_ms" in resolved
        if has_time and {"lat", "lon", "alt_agl"}.issubset(resolved.keys()):
            return resolved
    raise ValueError(
        f"unrecognised flight-log CSV: cannot find lat/lon/alt/time columns "
        f"in headers={headers!r}"
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _coerce_float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_mavic_csv(path: str | Path) -> list[GpsFix]:
    """Parse a flight-log CSV into a sorted list of GpsFix.

    Skips rows where lat / lon / time fail to parse — these are common at
    the head of a CSV before GPS lock.

    Raises:
      FileNotFoundError if `path` does not exist.
      ValueError if the file's headers don't match any known dialect.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    fixes: list[GpsFix] = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"flight-log CSV is empty: {p}")
        roles = _resolve_dialect(list(reader.fieldnames))

        for row in reader:
            lat = _coerce_float(row.get(roles["lat"]))
            lon = _coerce_float(row.get(roles["lon"]))
            agl = _coerce_float(row.get(roles["alt_agl"]))
            if lat is None or lon is None or agl is None:
                continue

            if "t_s" in roles:
                t = _coerce_float(row.get(roles["t_s"]))
            else:
                ms = _coerce_float(row.get(roles["t_ms"]))
                t = ms / 1000.0 if ms is not None else None
            if t is None:
                continue

            msl: float | None = None
            if "alt_msl" in roles:
                msl = _coerce_float(row.get(roles["alt_msl"]))

            # No-fix rows: DJI emits 0/0 before satellite lock.
            if lat == 0.0 and lon == 0.0:
                continue

            fixes.append(
                GpsFix(t_offset_s=t, lat=lat, lon=lon, alt_agl_m=agl, alt_msl_m=msl)
            )

    fixes.sort(key=lambda fx: fx.t_offset_s)
    return fixes


# ---------------------------------------------------------------------------
# Iterator interface — what the inference loop binds against.
# ---------------------------------------------------------------------------


class MavicFlightLog:
    """Random-access flight-log GPS source.

    Construction parses the CSV once. After that, `at(t_offset_s)` returns
    the fix nearest to (and not after) that timestamp — useful when the
    inference loop wants the GPS at frame t in a recorded video.

    Iteration yields all fixes in chronological order, so the e2e harness
    can drive a full simulated flight by `for fix in MavicFlightLog(...):`.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._fixes: list[GpsFix] = parse_mavic_csv(path)

    @property
    def path(self) -> Path:
        return self._path

    def __len__(self) -> int:
        return len(self._fixes)

    def __iter__(self) -> Iterator[GpsFix]:
        return iter(self._fixes)

    def fixes(self) -> list[GpsFix]:
        """Defensive copy of all fixes."""
        return list(self._fixes)

    def at(self, t_offset_s: float) -> GpsFix | None:
        """Latest fix at or before `t_offset_s`. None if `t_offset_s` is
        before the first sample."""
        if not self._fixes:
            return None
        # Binary search: bisect on `t_offset_s`.
        lo, hi = 0, len(self._fixes)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._fixes[mid].t_offset_s <= t_offset_s:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            return None
        return self._fixes[lo - 1]

    def stream(self, fixes: Iterable[GpsFix] | None = None) -> Iterator[GpsFix]:
        """Yield fixes one at a time. `fixes` override lets the e2e harness
        replay a synthetic subset."""
        return iter(fixes if fixes is not None else self._fixes)
