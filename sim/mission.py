"""Mission file parsing for the flight simulator.

A mission is a YAML document with home, airframe, flight params, an
ordered list of waypoints, an optional geofence polygon, and a flag for
return-to-home behaviour. See sim/missions/ for examples.

pyyaml is lazy-imported so `python -m sim.cli --help` works without it
installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import airframe as airframe_module
from .kinematics import haversine_m


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    alt_agl_m: float
    action: str = "capture"  # capture | hover | photo | none


@dataclass(frozen=True)
class HomePoint:
    lat: float
    lon: float
    alt_msl_m: float


@dataclass(frozen=True)
class FlightParams:
    altitude_agl_m: float
    cruise_speed_mps: float
    rgb_overlap_pct: float = 70.0


@dataclass(frozen=True)
class Mission:
    name: str
    zone_id: str
    home: HomePoint
    airframe_name: str
    flight_params: FlightParams
    waypoints: tuple[Waypoint, ...]
    return_to_home: bool = True
    geofence_polygon: tuple[tuple[float, float], ...] = field(default_factory=tuple)

    @property
    def airframe(self) -> airframe_module.AirframeProfile:
        return airframe_module.get(self.airframe_name)

    def total_ground_distance_m(self) -> float:
        """Sum of haversine legs along the planned path (incl. RTH)."""
        if not self.waypoints:
            return 0.0
        d = haversine_m(self.home.lat, self.home.lon,
                        self.waypoints[0].lat, self.waypoints[0].lon)
        for a, b in zip(self.waypoints, self.waypoints[1:]):
            d += haversine_m(a.lat, a.lon, b.lat, b.lon)
        if self.return_to_home:
            last = self.waypoints[-1]
            d += haversine_m(last.lat, last.lon, self.home.lat, self.home.lon)
        return d

    def estimated_flight_time_s(self) -> float:
        """Cruise distance / cruise speed. Excludes climb / hover time."""
        v = max(0.5, self.flight_params.cruise_speed_mps)
        return self.total_ground_distance_m() / v

    def battery_budget_ok(self, reserve_minutes: float = 5.0) -> bool:
        """True if estimated flight time fits in the airframe's battery budget."""
        budget_s = max(0.0, (self.airframe.battery_minutes - reserve_minutes) * 60.0)
        return self.estimated_flight_time_s() <= budget_s


def _coerce_waypoint(d: dict, default_alt_agl: float) -> Waypoint:
    return Waypoint(
        lat=float(d["lat"]),
        lon=float(d["lon"]),
        alt_agl_m=float(d.get("alt_agl_m", default_alt_agl)),
        action=str(d.get("action", "capture")),
    )


def parse_mission_dict(data: dict[str, Any]) -> Mission:
    """Build a Mission from an already-parsed dict."""
    if "home" not in data or "waypoints" not in data:
        raise ValueError("mission must have 'home' and 'waypoints'")
    home_dict = data["home"]
    home = HomePoint(
        lat=float(home_dict["lat"]),
        lon=float(home_dict["lon"]),
        alt_msl_m=float(home_dict.get("alt_msl_m", 0.0)),
    )
    fp_dict = data.get("flight_params", {})
    fp = FlightParams(
        altitude_agl_m=float(fp_dict.get("altitude_agl_m", 80.0)),
        cruise_speed_mps=float(fp_dict.get("cruise_speed_mps", 8.0)),
        rgb_overlap_pct=float(fp_dict.get("rgb_overlap_pct", 70.0)),
    )
    wps_in = data["waypoints"]
    if not wps_in:
        raise ValueError("mission must have at least one waypoint")
    waypoints = tuple(
        _coerce_waypoint(w, fp.altitude_agl_m) for w in wps_in
    )
    geo_in = data.get("geofence_polygon") or []
    geofence = tuple((float(p[0]), float(p[1])) for p in geo_in)
    return Mission(
        name=str(data.get("name", "unnamed-mission")),
        zone_id=str(data.get("zone_id", "unknown-zone")),
        home=home,
        airframe_name=str(data.get("airframe", "mavic_mini_2")),
        flight_params=fp,
        waypoints=waypoints,
        return_to_home=bool(data.get("return_to_home", True)),
        geofence_polygon=geofence,
    )


def load_mission(path: str | Path) -> Mission:
    """Load and parse a mission YAML file."""
    import yaml  # noqa: PLC0415 — lazy so --help works without pyyaml

    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"mission file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"mission file must contain a YAML mapping: {p}")
    return parse_mission_dict(data)
