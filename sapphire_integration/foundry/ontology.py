"""Foundry ontology object definitions for wildfire-watch.

Six new ontology types + reuse of existing Sapphire `Alert` + `Incident`.
Mirrors the design in docs/intel/foundry-research-2026-05-01.md (Section 4
"Recommended ontology"). The actual Foundry ontology is defined in TypeScript
through Foundry's Ontology Manager; this Python module is the local-source-of-
truth + serializer that produces the JSON payloads ingested via Sapphire's
existing `lib/foundry/ingestion.py` daemon.

Why have a Python copy? Because the wildfire-watch repo is the upstream of
truth for the schema; Foundry pulls from us, not the other way around. If
Foundry access is denied or revoked, this module + the PostGIS adapter is
still a working ontology layer.

Status (2026-05-02): These are stubs. They serialize cleanly and round-trip
through `to_json/from_json`, but the actual Foundry-side bindings haven't
been wired yet (gated on Developer Tier approval per the outreach kit's
Email 5).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Ontology objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Drone:
    """Airframe + RPIC + insurance + maintenance metadata.

    Foundry name: `wfw.Drone`. Primary key: drone_id (regex ^wfw-[a-z0-9]{4,16}$).
    """

    drone_id: str
    airframe_class: Literal[
        "mavic_mini_2",
        "holybro_x500_v2",
        "skydio_x10",
        "teal_2",
        "parrot_anafi_usa_gov",
        "generic_quad",
        "sim_only",
    ]
    rpic_pilot_license_id: str | None  # FAA Part 107 cert # if real airframe
    insurance_policy_ref: str | None
    maintenance_log_uri: str | None
    blue_uas_status: Literal["cleared", "substitutable", "non_eligible", "unknown"] = "unknown"
    registered_at: str = field(default_factory=_utcnow_iso)


@dataclass(frozen=True)
class Zone:
    """A monitored polygon. GeoJSON-encoded geometry + fuel-load metadata.

    Foundry name: `wfw.Zone`. Cross-references the
    `missions/zones/<corridor>.geojson` files.
    """

    zone_id: str  # e.g. "slate-river-drainage"
    corridor: str  # e.g. "gunnison-crested-butte-corridor"
    polygon_geojson: dict  # GeoJSON Feature payload
    fuel_load_class: Literal["low", "moderate", "moderate-high", "high", "extreme"]
    primary_risk: str
    elevation_min_m: float
    elevation_max_m: float
    last_patrol_at: str | None = None
    is_exclusion: bool = False
    regulatory_basis: str | None = None  # e.g. "36 CFR 261.16" if exclusion


@dataclass(frozen=True)
class FireDepartmentUnit:
    """A partner fire department / coordinator agency.

    Foundry name: `wfw.FireDepartmentUnit`. Used for both notification routing
    and the `letters_of_authorization_count` KPI snapshot.
    """

    unit_id: str  # e.g. "cbfpd"
    name: str
    aor_geojson: dict  # area of responsibility polygon
    primary_contact_name: str | None
    primary_contact_role: str | None
    dispatch_phone: str | None
    physical_address: str | None
    engagement_status: Literal["not_contacted", "outreached", "engaged", "loa_signed", "operational_partner"] = "not_contacted"
    last_contact_at: str | None = None


@dataclass(frozen=True)
class FlightLog:
    """One flight session — sim or real.

    Foundry name: `wfw.FlightLog`. Pulls together drone + mission + recorded
    telemetry into one object.
    """

    flight_id: str = field(default_factory=_new_uuid)
    drone_id: str = ""
    mission_yaml_uri: str = ""
    started_at: str = field(default_factory=_utcnow_iso)
    ended_at: str | None = None
    is_sim: bool = True
    recording_dir_uri: str | None = None
    total_distance_km: float = 0.0
    total_duration_s: float = 0.0
    signals_emitted: int = 0
    consensus_signals_emitted: int = 0
    geofence_breaches: int = 0
    battery_consumed_pct: float = 0.0


@dataclass(frozen=True)
class BatteryCycle:
    """One battery cycle. For maintenance + airworthiness tracking.

    Foundry name: `wfw.BatteryCycle`.
    """

    cycle_id: str = field(default_factory=_new_uuid)
    battery_serial: str = ""
    chemistry: Literal["lipo", "li_ion", "lifepo4", "unknown"] = "unknown"
    capacity_mah: int = 0
    flight_id: str | None = None
    started_at: str = field(default_factory=_utcnow_iso)
    ended_at: str | None = None
    starting_voltage_v: float = 0.0
    ending_voltage_v: float = 0.0
    coldest_temp_c: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class WildfireSignal:
    """The v1 wildfire_signal as a Foundry ontology object.

    Foundry name: `wfw.WildfireSignal`. Mirrors
    `sapphire_integration/wildfire_signal_schema.json` v1.0.0. Serialized
    payload is identical to the v1 JSON; this dataclass is just the typed
    Python view.
    """

    signal_id: str
    drone_id: str
    zone_id: str
    timestamp: str
    coords_lat: float
    coords_lon: float
    coords_alt_agl_m: float
    signal_type: Literal["smoke", "fire", "thermal_anomaly", "wildlife", "anomaly", "system_event"]
    confidence: float
    risk_score: float
    recommended_action: Literal[
        "log_only", "notify_operator", "notify_fire_dept", "loiter_and_capture", "rtl"
    ]
    schema_version: str = SCHEMA_VERSION

    # Optional fields (full v1 payload retained for round-trip)
    raw_payload: dict | None = None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def to_foundry_json(obj: Any) -> str:
    """Serialize an ontology object to a Foundry-compatible JSON string.

    Foundry's ingest API accepts JSON arrays of {properties, ...} objects;
    this helper produces one entry. The shape is:

        {
          "type": "<Foundry object type>",
          "primaryKey": "<id>",
          "properties": { ... }
        }
    """
    if not hasattr(obj, "__dataclass_fields__"):
        raise TypeError(f"to_foundry_json requires a dataclass instance, got {type(obj)}")

    type_map = {
        "Drone": "wfw.Drone",
        "Zone": "wfw.Zone",
        "FireDepartmentUnit": "wfw.FireDepartmentUnit",
        "FlightLog": "wfw.FlightLog",
        "BatteryCycle": "wfw.BatteryCycle",
        "WildfireSignal": "wfw.WildfireSignal",
    }

    obj_type = type_map.get(type(obj).__name__)
    if obj_type is None:
        raise TypeError(f"unknown ontology type: {type(obj).__name__}")

    properties = asdict(obj)
    pk_field = _primary_key_field(type(obj).__name__)
    pk = properties.get(pk_field)
    if pk is None:
        raise ValueError(f"object missing primary key field {pk_field}")

    envelope = {"type": obj_type, "primaryKey": pk, "properties": properties}
    return json.dumps(envelope, separators=(",", ":"))


def from_foundry_json(payload: str) -> Any:
    """Reverse of `to_foundry_json`. Round-trips."""
    envelope = json.loads(payload)
    obj_type = envelope.get("type")
    properties = envelope.get("properties") or {}

    cls_map = {
        "wfw.Drone": Drone,
        "wfw.Zone": Zone,
        "wfw.FireDepartmentUnit": FireDepartmentUnit,
        "wfw.FlightLog": FlightLog,
        "wfw.BatteryCycle": BatteryCycle,
        "wfw.WildfireSignal": WildfireSignal,
    }
    cls = cls_map.get(obj_type)
    if cls is None:
        raise ValueError(f"unknown Foundry type: {obj_type}")

    return cls(**properties)


def _primary_key_field(class_name: str) -> str:
    return {
        "Drone": "drone_id",
        "Zone": "zone_id",
        "FireDepartmentUnit": "unit_id",
        "FlightLog": "flight_id",
        "BatteryCycle": "cycle_id",
        "WildfireSignal": "signal_id",
    }[class_name]


# ---------------------------------------------------------------------------
# Adapters from existing data sources
# ---------------------------------------------------------------------------


def wildfire_signal_from_v1(v1_payload: dict) -> WildfireSignal:
    """Convert a v1 wildfire_signal JSON dict into a WildfireSignal ontology object."""
    coords = v1_payload.get("coords") or {}
    return WildfireSignal(
        signal_id=v1_payload["signal_id"],
        drone_id=v1_payload["drone_id"],
        zone_id=v1_payload["zone_id"],
        timestamp=v1_payload["timestamp"],
        coords_lat=float(coords.get("lat", 0.0)),
        coords_lon=float(coords.get("lon", 0.0)),
        coords_alt_agl_m=float(coords.get("alt_agl_m", 0.0)),
        signal_type=v1_payload["signal_type"],
        confidence=float(v1_payload["confidence"]),
        risk_score=float(v1_payload["risk_score"]),
        recommended_action=v1_payload["recommended_action"],
        schema_version=v1_payload.get("schema_version", SCHEMA_VERSION),
        raw_payload=v1_payload,
    )


def zone_from_geojson_feature(feature: dict, corridor: str) -> Zone:
    """Convert a GeoJSON Feature (from missions/zones/*.geojson) to a Zone object."""
    props = feature.get("properties") or {}
    return Zone(
        zone_id=props["zone_id"],
        corridor=corridor,
        polygon_geojson=feature,
        fuel_load_class=props.get("fuel_load_class", "moderate"),
        primary_risk=props.get("primary_risk", "unknown"),
        elevation_min_m=float(props.get("elevation_min_m", 0.0)),
        elevation_max_m=float(props.get("elevation_max_m", 0.0)),
        is_exclusion=bool(props.get("exclusion", False)),
        regulatory_basis=props.get("regulatory_basis"),
    )


__all__ = [
    "SCHEMA_VERSION",
    "Drone",
    "Zone",
    "FireDepartmentUnit",
    "FlightLog",
    "BatteryCycle",
    "WildfireSignal",
    "to_foundry_json",
    "from_foundry_json",
    "wildfire_signal_from_v1",
    "zone_from_geojson_feature",
]
