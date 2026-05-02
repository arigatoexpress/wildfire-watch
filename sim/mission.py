"""Mission file parsing for the flight simulator.

A mission is a YAML document with home, airframe, flight params, an
ordered list of waypoints, an optional geofence (inclusion + exclusions),
and a flag for return-to-home behaviour. See sim/missions/ for examples.

Geofence YAML schema (Phase 0.5+):

    geofence:
      inclusion: [[lat, lon], ...]
      exclusions:
        - name: west-elk-wilderness
          polygon: [[lat, lon], ...]
          regulatory_basis: "36 CFR 261.16"
          # optional: type: hard (default) | warn

Or pull from missions/zones/*.geojson by feature_id:

    geofence:
      inclusion_from_zone: <geojson-stem>:<zone_id>
      exclusion_from_zone:
        - <geojson-stem>:<zone_id>
        - <geojson-stem>:<zone_id>

Backwards compat: missions that still use the legacy `geofence_polygon:`
top-level key get an inclusion-only geofence with no exclusions.

pyyaml is lazy-imported so `python -m sim.cli --help` works without it
installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import airframe as airframe_module
from .geofence import (
    Geofence,
    geofence_from_polygon,
    polygons_from_geojson_feature,
)
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
class GeofenceExclusion:
    """One named exclusion polygon with regulatory metadata.

    `kind` is "hard" (default) for absolute no-fly (Wilderness, TFR) or
    "warn" for soft regions that still permit flight but should emit a
    warning event (e.g. KGUC Class E surface area — LAANC-required but
    not a hard prohibition without authorization).
    """

    name: str
    polygon: tuple[tuple[float, float], ...]
    regulatory_basis: str = ""
    kind: str = "hard"  # hard | warn


@dataclass(frozen=True)
class Mission:
    name: str
    zone_id: str
    home: HomePoint
    airframe_name: str
    flight_params: FlightParams
    waypoints: tuple[Waypoint, ...]
    return_to_home: bool = True
    # Legacy single inclusion-polygon, kept for back-compat.
    geofence_polygon: tuple[tuple[float, float], ...] = field(default_factory=tuple)
    # Phase 0.5+ structured geofence.
    geofence: Geofence = field(default_factory=Geofence)
    exclusions: tuple[GeofenceExclusion, ...] = field(default_factory=tuple)

    @property
    def airframe(self) -> airframe_module.AirframeProfile:
        return airframe_module.get(self.airframe_name)

    def hard_exclusions(self) -> tuple[GeofenceExclusion, ...]:
        return tuple(e for e in self.exclusions if e.kind == "hard")

    def warn_exclusions(self) -> tuple[GeofenceExclusion, ...]:
        return tuple(e for e in self.exclusions if e.kind == "warn")

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


# Resolution roots for `*_from_zone:` references.
_ZONES_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "missions" / "zones"


def _zones_root() -> Path:
    return _ZONES_DIR_DEFAULT


def _load_zone_polygon(ref: str) -> tuple[tuple[float, float], ...]:
    """Resolve a "<geojson-stem>:<zone_id>" reference to a closed
    (lat, lon) ring.

    Looks for `missions/zones/<stem>.geojson` and finds the feature whose
    `properties.zone_id == <zone_id>`. Returns the outer ring as a tuple
    of (lat, lon) vertices. Raises if the stem or zone_id are missing.
    """
    import json  # noqa: PLC0415

    if ":" not in ref:
        raise ValueError(
            f"zone reference must be 'stem:zone_id'; got {ref!r}"
        )
    stem, zone_id = ref.split(":", 1)
    path = _zones_root() / f"{stem}.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"zones file not found for ref {ref!r}: {path}"
        )
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj.get("features", []) or []:
        props = feat.get("properties") or {}
        if props.get("zone_id") == zone_id:
            rings = polygons_from_geojson_feature(feat)
            if not rings:
                raise ValueError(
                    f"feature {ref!r} has no Polygon geometry"
                )
            return tuple(rings[0])
    raise ValueError(
        f"zone_id {zone_id!r} not found in {path}"
    )


def _build_geofence(
    data: dict[str, Any],
) -> tuple[Geofence, tuple[GeofenceExclusion, ...]]:
    """Parse the structured `geofence:` block (or fall back to the legacy
    `geofence_polygon:` top-level key).

    Returns (Geofence, list-of-named-exclusions). The Geofence carries
    just the polygon math; the list-of-named-exclusions retains the
    `name`, `regulatory_basis`, and `kind` metadata for runner
    diagnostics.
    """
    g_dict = data.get("geofence")
    exclusions: list[GeofenceExclusion] = []

    if g_dict is None:
        # Legacy fallback.
        geo_in = data.get("geofence_polygon") or []
        legacy = tuple((float(p[0]), float(p[1])) for p in geo_in)
        return geofence_from_polygon(legacy), tuple(exclusions)

    if not isinstance(g_dict, dict):
        raise ValueError("'geofence' must be a YAML mapping")

    # Inclusion: explicit polygon OR a zone reference.
    inclusion_pts: tuple[tuple[float, float], ...] = ()
    if "inclusion" in g_dict and g_dict["inclusion"]:
        inclusion_pts = tuple(
            (float(p[0]), float(p[1])) for p in g_dict["inclusion"]
        )
    elif "inclusion_from_zone" in g_dict and g_dict["inclusion_from_zone"]:
        inclusion_pts = _load_zone_polygon(str(g_dict["inclusion_from_zone"]))

    # Exclusions: explicit list of {name, polygon, regulatory_basis, type}
    # plus zero or more zone references via exclusion_from_zone.
    raw_excl = g_dict.get("exclusions") or []
    for e in raw_excl:
        if not isinstance(e, dict):
            raise ValueError("each entry in geofence.exclusions must be a mapping")
        poly = tuple((float(p[0]), float(p[1])) for p in e.get("polygon") or [])
        if not poly:
            raise ValueError(
                f"geofence exclusion {e.get('name')!r} has no polygon"
            )
        kind = str(e.get("type", "hard")).lower()
        if kind not in ("hard", "warn"):
            raise ValueError(
                f"geofence exclusion 'type' must be 'hard' or 'warn'; got {kind!r}"
            )
        exclusions.append(
            GeofenceExclusion(
                name=str(e.get("name", "unnamed-exclusion")),
                polygon=poly,
                regulatory_basis=str(e.get("regulatory_basis", "")),
                kind=kind,
            )
        )

    for ref in g_dict.get("exclusion_from_zone") or []:
        ref_str = str(ref)
        poly = _load_zone_polygon(ref_str)
        # Cross-reference back into the source zones file for metadata.
        meta_name, meta_basis, meta_kind = _zone_metadata(ref_str)
        exclusions.append(
            GeofenceExclusion(
                name=meta_name,
                polygon=poly,
                regulatory_basis=meta_basis,
                kind=meta_kind,
            )
        )

    fence = Geofence(
        inclusion=inclusion_pts,
        exclusions=tuple(e.polygon for e in exclusions if e.kind == "hard"),
    )
    return fence, tuple(exclusions)


def _zone_metadata(ref: str) -> tuple[str, str, str]:
    """Look up `(name, regulatory_basis, kind)` for a zone reference.

    `kind` defaults to "hard" if `properties.exclusion` is true and the
    feature has a regulatory_basis; otherwise "warn". This mirrors the
    convention in missions/zones/gunnison_crested_butte_corridor.geojson
    where `west-elk-wilderness-exclusion` has `exclusion: true` (hard)
    and `kguc-class-e-surface-area` has `exclusion: false` (warn).
    """
    import json  # noqa: PLC0415

    stem, zone_id = ref.split(":", 1)
    path = _zones_root() / f"{stem}.geojson"
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj.get("features", []) or []:
        props = feat.get("properties") or {}
        if props.get("zone_id") == zone_id:
            kind = "hard" if props.get("exclusion") else "warn"
            return (
                str(zone_id),
                str(props.get("regulatory_basis", "")),
                kind,
            )
    return (zone_id, "", "hard")


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
    geofence, exclusions = _build_geofence(data)
    # Keep the legacy `geofence_polygon` field populated for any caller
    # still using it (the swarm runner does, until we update it below).
    legacy_polygon = tuple(geofence.inclusion)
    return Mission(
        name=str(data.get("name", "unnamed-mission")),
        zone_id=str(data.get("zone_id", "unknown-zone")),
        home=home,
        airframe_name=str(data.get("airframe", "mavic_mini_2")),
        flight_params=fp,
        waypoints=waypoints,
        return_to_home=bool(data.get("return_to_home", True)),
        geofence_polygon=legacy_polygon,
        geofence=geofence,
        exclusions=exclusions,
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
