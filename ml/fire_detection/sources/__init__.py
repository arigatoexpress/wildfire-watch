"""GPS / pose sources for the on-drone inference loop.

A "source" is anything that yields `(timestamp, lat, lon, alt_agl_m)` tuples.
Phase 0 hardware (DJI Mavic Mini) does not expose a live MAVLink stream, so
inference can only fuse against a flight log exported after landing. Phase 1
hardware (Holybro X500 + Cube Orange+) WILL expose live MAVLink, at which
point a live `MavlinkSource` joins this module.

Today this module exposes:
  - `MavicFlightLog` — parses CSV exports from DJI Fly / Airdata / DatCon
    and yields `GpsFix` samples by timestamp.
"""

from ml.fire_detection.sources.mavic_log import (  # noqa: F401
    MavicFlightLog,
    GpsFix,
    parse_mavic_csv,
)
