"""Mock terrain-relative-navigation (TRN) sensor.

Concept: every N seconds, "capture" a downward-looking patch and match it
against a pre-loaded DEM / orthoimagery tile (USGS 1/3 arc-second is the
public reference). On a successful match the sensor returns an absolute
(lat, lon) correction; on failure it returns nothing.

Match success conditions modeled here:

  - canopy_density   in [0, 1]   forest canopy obscures ground texture
  - smoke_density    in [0, 1]   smoke obscures everything
  - water_fraction   in [0, 1]   water bodies don't have stable features
  - altitude_agl_m   meters      < 30 m: too low (camera FOV too narrow)
                                 > 250 m: too high (DEM resolution wins)

If any of canopy_density, smoke_density, water_fraction is >= 0.7 OR
altitude is outside [30, 250], we declare NO_LOCK. Otherwise we return
the truth position perturbed by a Gaussian (sigma 5 m on each axis).
This 5 m is the public-claim CEP for OSCAR-class systems matching
against satellite tiles.

We do NOT actually load a DEM. We do NOT do any cross-correlation. We
trust the caller to pass us a "truth" that the matcher would, in the
real world, recover.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


_LOCK_LOST_OBSCURATION_THRESHOLD = 0.7
_MIN_USEFUL_ALTITUDE_M = 30.0
_MAX_USEFUL_ALTITUDE_M = 250.0
_TRN_SIGMA_M = 5.0


@dataclass
class TRNReading:
    """Per-update TRN output."""

    lat: float
    lon: float
    sigma_m: float
    lock_ok: bool


class TerrainRelativeNav:
    """Mock TRN sensor — emits a corrected absolute position on a cadence."""

    def __init__(self, seed: int = 0, update_period_s: float = 2.0):
        self._rng = random.Random(seed)
        self.update_period_s = update_period_s
        self._t_since_last_update_s = 0.0
        self._last_reading: TRNReading | None = None

    def step(
        self,
        *,
        dt: float,
        truth_lat: float,
        truth_lon: float,
        altitude_agl_m: float,
        canopy_density: float = 0.0,
        smoke_density: float = 0.0,
        water_fraction: float = 0.0,
    ) -> TRNReading | None:
        """Advance by `dt`. Returns a fresh reading if it's update time
        AND the matcher would lock; otherwise returns None.

        The fusion filter should treat None as "no new TRN info this
        tick" and rely on whatever it had before.
        """
        self._t_since_last_update_s += dt
        if self._t_since_last_update_s < self.update_period_s:
            return None
        self._t_since_last_update_s = 0.0

        if (
            canopy_density >= _LOCK_LOST_OBSCURATION_THRESHOLD
            or smoke_density >= _LOCK_LOST_OBSCURATION_THRESHOLD
            or water_fraction >= _LOCK_LOST_OBSCURATION_THRESHOLD
            or altitude_agl_m < _MIN_USEFUL_ALTITUDE_M
            or altitude_agl_m > _MAX_USEFUL_ALTITUDE_M
        ):
            self._last_reading = TRNReading(
                lat=truth_lat,
                lon=truth_lon,
                sigma_m=float("inf"),
                lock_ok=False,
            )
            return self._last_reading

        # Lock OK. Perturb truth by Gaussian on each axis. Convert
        # 5 m to degrees: 1 deg lat = ~111_320 m everywhere; 1 deg lon
        # at latitude phi = 111_320 * cos(phi).
        nx_m = self._gauss() * _TRN_SIGMA_M
        ny_m = self._gauss() * _TRN_SIGMA_M
        dlat = ny_m / 111_320.0
        cos_phi = max(1e-6, math.cos(math.radians(truth_lat)))
        dlon = nx_m / (111_320.0 * cos_phi)
        reading = TRNReading(
            lat=truth_lat + dlat,
            lon=truth_lon + dlon,
            sigma_m=_TRN_SIGMA_M,
            lock_ok=True,
        )
        self._last_reading = reading
        return reading

    def _gauss(self) -> float:
        u1 = max(1e-12, self._rng.random())
        u2 = self._rng.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
