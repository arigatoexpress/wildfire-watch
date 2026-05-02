"""CoT type-code dictionary for wildfire-watch signal categories.

Cursor-on-Target type codes are dotted (or dashed) strings that classify what
the marker on the map represents. The first letter is the *atom* class:

  a  atom (a track / unit; affiliation in 2nd char: f friend, h hostile,
                                                    n neutral, u unknown)
  b  bit  (a bit of information / event — fire, weather, NBC sensor reading)
  t  tasking
  r  reply / report
  c  capability
  u  user-defined / drawing

The remaining characters form a hierarchy. References:

- MITRE TR-04-08 / "Cursor on Target Message Router User's Guide" — the
  original public spec from MITRE that defines `<event>`/`<point>`/`<detail>`
  and the type-code grammar.
- TAK.gov developer resources publish the canonical `cot-types.xml`
  enumeration used by ATAK / WinTAK clients.
- Community references (takmaps.com, FreeTAKServer docs) catalog the
  bit-class fire codes (b-r-f-h-*) used by ATAK's wildland-fire plugins.

Choices below are pragmatic. CoT is a "best effort" classification system;
when in doubt we pick a code that renders meaningfully on stock ATAK + adds
descriptive remarks rather than inventing a non-portable code.
"""

from __future__ import annotations

from typing import Any

# Public mapping: wildfire_signal.signal_type -> CoT type code.
#
# Why these specific codes:
#
#   smoke              b-r-f-h-s   "bit, report, fire, hot, smoke" — ATAK's
#                                  smoke / column marker.
#   fire               b-r-f-h-c   "bit, report, fire, hot, confirmed" — used
#                                  for confirmed flame (RGB+thermal fused).
#   thermal_anomaly    b-r-f-h-h   "bit, report, fire, hot, hot-spot" — used
#                                  for IR-only thermal hits where RGB hasn't
#                                  confirmed flame.
#   wildlife           a-n-G       "atom, neutral, ground" — neutral track on
#                                  the ground. Wildlife is *not* friendly
#                                  (we don't command it) and *not* hostile.
#   anomaly            b-d         "bit, detection" — generic anomaly.
#   system_event       b-m-p-s-m   "bit, machine, position, status, message"
#                                  — system status / housekeeping marker.
#
SIGNAL_TYPE_TO_COT_TYPE: dict[str, str] = {
    "smoke": "b-r-f-h-s",
    "fire": "b-r-f-h-c",
    "thermal_anomaly": "b-r-f-h-h",
    "wildlife": "a-n-G",
    "anomaly": "b-d",
    "system_event": "b-m-p-s-m",
}

# Drone self-position. ATAK has no stable "rotary UAS friendly" code that
# every client renders identically; the closest portable choice is
# `a-f-A-M-F-Q-r` (atom, friend, Air, Military, Fixed-wing... Q rotary).
# Many ATAK builds normalize unknown subtypes back to a-f-A so this still
# shows up as a friendly aircraft icon. Document the trade-off and let the
# operator override.
DRONE_SELF_POSITION_COT_TYPE = "a-f-A-M-F-Q-r"

# Geofence / drawing. CoT has a convention `u-d-c-c` ("user-defined,
# drawing, closed-shape") for arbitrary closed polygons. ATAK draws this as
# an outlined polygon. For wildfire AOR boundaries this is the right
# default; the operator can override with `u-d-r` for rectangles or
# `u-d-c` for ellipses.
GEOFENCE_POLYGON_COT_TYPE = "u-d-c-c"


# Reverse lookup table for human-readable descriptions, used by the CLI's
# debug output and for round-trip tests.
COT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "b-r-f-h-s": "fire/hot/smoke (smoke column or plume)",
    "b-r-f-h-c": "fire/hot/confirmed (RGB+thermal fused flame)",
    "b-r-f-h-h": "fire/hot/hot-spot (thermal anomaly, IR only)",
    "a-n-G": "atom/neutral/ground (wildlife / unknown ground track)",
    "b-d": "bit/detection (generic anomaly)",
    "b-m-p-s-m": "bit/machine/position/status/message (system event)",
    "a-f-A-M-F-Q-r": "atom/friend/Air/Military/Fixed-wing/Q-rotary (drone)",
    "u-d-c-c": "user-defined/drawing/closed-shape (geofence polygon)",
}


# Stale-window defaults (seconds). These are the time-from-event after which
# the marker is considered "stale" by ATAK clients (greys out / drops). Keep
# them tuned to the signal's real-world half-life.
STALE_SECONDS_BY_SIGNAL_TYPE: dict[str, int] = {
    "fire": 3600,            # 1 hour — flame persists, but resend often
    "smoke": 3600,           # 1 hour — plume drifts; conservative
    "thermal_anomaly": 900,  # 15 min — IR-only hits are noisy
    "wildlife": 900,         # 15 min — animals move
    "anomaly": 1800,         # 30 min — broad bucket
    "system_event": 86400,   # 24 hours — slow housekeeping
}
DEFAULT_STALE_SECONDS = 3600


def cot_type_for_signal(signal: dict[str, Any]) -> str:
    """Return the CoT type code for a wildfire_signal v1 record.

    Falls back to `b-d` (generic detection) if `signal_type` is unknown so
    we never produce malformed XML.
    """
    return SIGNAL_TYPE_TO_COT_TYPE.get(signal.get("signal_type", ""), "b-d")


def stale_seconds_for_signal(signal: dict[str, Any]) -> int:
    """Return the stale-window in seconds for the given signal."""
    return STALE_SECONDS_BY_SIGNAL_TYPE.get(
        signal.get("signal_type", ""), DEFAULT_STALE_SECONDS,
    )


def describe_cot_type(cot_type: str) -> str:
    """Human-readable description of a CoT type code (best effort)."""
    return COT_TYPE_DESCRIPTIONS.get(cot_type, f"unknown CoT type: {cot_type}")
