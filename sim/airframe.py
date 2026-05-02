"""Airframe profiles for the flight simulator.

Mavic Mini 2 is the canonical Phase 0 airframe (matches the post-flight
SRT format the rest of the wildfire-watch pipeline already accepts).
Holybro X500 v2 + a generic quad are included for forward-compatibility
with the Phase 1 / Phase 2 hardware tracks documented in
docs/20-hardware-bom.md.

Numbers are conservative manufacturer specs, not best-case marketing
peaks. They are intended to be plausible bounds for the kinematic
integrator, not certified flight envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AirframeProfile:
    """Static performance envelope of a multirotor."""

    name: str
    max_horizontal_speed_mps: float
    max_climb_rate_mps: float
    cruise_speed_mps: float
    service_ceiling_agl_m: float
    battery_minutes: float
    wind_resistance_mps: float
    mass_kg: float


MAVIC_MINI_2 = AirframeProfile(
    name="mavic_mini_2",
    # DJI spec: 16 m/s sport mode horizontal.
    max_horizontal_speed_mps=16.0,
    # DJI spec: 5 m/s ascent, 4 m/s descent — use the conservative side.
    max_climb_rate_mps=4.0,
    # Reasonable cruise for survey work.
    cruise_speed_mps=8.0,
    # FAA Part 107 ceiling (drone is rated higher; this is the legal cap).
    service_ceiling_agl_m=120.0,
    # DJI spec: 31 minutes nominal.
    battery_minutes=31.0,
    # Level 5 wind tolerance ~10.5 m/s.
    wind_resistance_mps=10.5,
    mass_kg=0.249,
)

HOLYBRO_X500_V2 = AirframeProfile(
    name="holybro_x500_v2",
    max_horizontal_speed_mps=20.0,
    max_climb_rate_mps=5.0,
    cruise_speed_mps=10.0,
    service_ceiling_agl_m=120.0,
    battery_minutes=22.0,
    wind_resistance_mps=12.0,
    mass_kg=2.0,
)

GENERIC_QUAD = AirframeProfile(
    name="generic_quad",
    max_horizontal_speed_mps=15.0,
    max_climb_rate_mps=4.0,
    cruise_speed_mps=8.0,
    service_ceiling_agl_m=120.0,
    battery_minutes=20.0,
    wind_resistance_mps=10.0,
    mass_kg=1.5,
)


_REGISTRY = {
    "mavic_mini_2": MAVIC_MINI_2,
    "holybro_x500_v2": HOLYBRO_X500_V2,
    "generic_quad": GENERIC_QUAD,
}


def get(name: str) -> AirframeProfile:
    """Look up an airframe profile by name. Raises KeyError if unknown."""
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"unknown airframe '{name}'; known: {known}")
    return _REGISTRY[name]


def all_names() -> list[str]:
    return sorted(_REGISTRY.keys())
