"""Build a Cursor-on-Target XML event from a wildfire_signal v1 record.

CoT canonical structure (CoT 2.0):

    <event version="2.0"
           uid="<unique-id>"
           type="<dotted-type-code>"
           how="<source-quality>"
           time="<emit-utc>"
           start="<valid-from-utc>"
           stale="<valid-until-utc>">
      <point lat="..." lon="..." hae="..." ce="..." le="..."/>
      <detail>
        ...arbitrary children, see ATAK plugins...
      </detail>
    </event>

We populate:

  - ``event/@uid``     wfw-detection-<signal_id>
  - ``event/@type``    from cot_types.cot_type_for_signal(signal)
  - ``event/@how``     m-g for machine-derived geolocated; we use this for
                       all drone-emitted signals.
  - ``event/@time/@start/@stale``  ISO 8601 Z; stale = time + window from
                                    cot_types.stale_seconds_for_signal.
  - ``point/@lat/@lon`` from target_coords if present, else coords.
  - ``point/@hae``      height above ellipsoid (meters MSL is the standard
                        approximation; CoT does not differentiate at this
                        precision for first-responder use).
  - ``point/@ce``       circular error 90% in meters.
  - ``point/@le``       linear (vertical) error in meters.
  - ``detail/contact/@callsign``  ``WFW-<unit-suffix> <subtype-or-type> <conf%>``
  - ``detail/remarks``           human-readable triage line.
  - ``detail/__group``           ATAK group / role (Magenta / HQ for SA).
  - ``detail/takv``              client identification (SA discovery).
  - ``detail/_flow-tags_``       routing tags (empty by default).
  - ``detail/link``              parent link to the drone's own track.
  - ``detail/archive``           tells the TAK Server to log this event.

Stdlib ``xml.etree.ElementTree`` only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

from . import cot_types

# Top-level constants. Bump COT_EMITTER_VERSION on breaking changes to the
# generated XML shape.
COT_VERSION = "2.0"
COT_HOW_MACHINE_GPS = "m-g"
COT_EMITTER_PLATFORM = "wfw-cot-emitter"
COT_EMITTER_DEVICE = "wildfire-watch"
COT_EMITTER_VERSION = "0.1.0"
COT_DEFAULT_GROUP_NAME = "Magenta"
COT_DEFAULT_GROUP_ROLE = "HQ"
COT_DEFAULT_CE_METERS = 25.0
COT_DEFAULT_LE_METERS = 50.0


def _utc_iso(dt: datetime) -> str:
    """ISO 8601 with trailing Z (CoT-canonical, no '+00:00')."""
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_signal_timestamp(ts: str | None) -> datetime:
    """Parse a wildfire_signal timestamp; fallback to now() on missing/bad."""
    if not ts:
        return datetime.now(UTC)
    try:
        # Accept both "...Z" and "...+00:00" forms.
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


def _select_point_coords(signal: dict[str, Any]) -> tuple[float, float, float]:
    """Pick (lat, lon, hae) from target_coords if present else coords.

    HAE (Height Above Ellipsoid) — we use ``alt_msl_m`` if present (close
    enough for first-responder use), else fall back to drone ``alt_msl_m``,
    else 0.
    """
    target = signal.get("target_coords") or {}
    coords = signal.get("coords") or {}

    if "lat" in target and "lon" in target:
        lat = float(target["lat"])
        lon = float(target["lon"])
        hae_src = target.get("alt_msl_m", coords.get("alt_msl_m", 0.0))
    else:
        lat = float(coords.get("lat", 0.0))
        lon = float(coords.get("lon", 0.0))
        hae_src = coords.get("alt_msl_m", 0.0)
    return lat, lon, float(hae_src or 0.0)


def _select_ce(signal: dict[str, Any]) -> float:
    """Circular error 90% (meters)."""
    target = signal.get("target_coords") or {}
    if "horizontal_uncertainty_m" in target and target["horizontal_uncertainty_m"] is not None:
        return float(target["horizontal_uncertainty_m"])
    return COT_DEFAULT_CE_METERS


def _select_le(signal: dict[str, Any]) -> float:
    """Linear (vertical) error in meters. No vertical uncertainty in v1
    schema, so use the default."""
    return COT_DEFAULT_LE_METERS


def _build_callsign(signal: dict[str, Any]) -> str:
    """Build a TAK callsign for the marker (≤ 24 chars).

    Format: ``WFW-<unit-suffix> <subtype-or-type> <conf%>``

    Examples:
        WFW-unit01 smoke 86%
        WFW-unit01 wildlife/elk 91%
        WFW-unit01 fire 99%
    """
    drone_id = signal.get("drone_id") or "wfw-unknown"
    suffix = drone_id[len("wfw-"):] if drone_id.startswith("wfw-") else drone_id

    subtype = signal.get("signal_subtype") or signal.get("signal_type") or "signal"
    conf_raw = signal.get("confidence")
    try:
        conf_pct = int(round(float(conf_raw) * 100)) if conf_raw is not None else 0
    except (TypeError, ValueError):
        conf_pct = 0

    cs = f"WFW-{suffix} {subtype} {conf_pct}%"
    if len(cs) <= 24:
        return cs

    # Truncate while keeping the trailing confidence; truncate the subtype.
    head = f"WFW-{suffix} "
    tail = f" {conf_pct}%"
    available = 24 - len(head) - len(tail)
    if available < 1:
        # Last-ditch: drop subtype.
        cs2 = f"WFW-{suffix}{tail}"
        return cs2[:24]
    return head + subtype[:available] + tail


def _build_remarks(signal: dict[str, Any]) -> str:
    """Compose a single-line human-readable remarks string."""
    bits: list[str] = []
    evidence = signal.get("evidence") or {}
    model = evidence.get("model_outputs") or {}

    if "rgb_yolo_score" in model and model["rgb_yolo_score"] is not None:
        bits.append(f"RGB {float(model['rgb_yolo_score']):.2f}")
    if "thermal_delta_c" in model and model["thermal_delta_c"] is not None:
        bits.append(f"thermal d{float(model['thermal_delta_c']):.1f}C")
    if "thermal_max_temp_c" in model and model["thermal_max_temp_c"] is not None:
        bits.append(f"max {float(model['thermal_max_temp_c']):.1f}C")
    if "wildlife_class" in model and model["wildlife_class"]:
        bits.append(f"class {model['wildlife_class']}")

    drone_id = signal.get("drone_id")
    if drone_id:
        bits.append(f"drone {drone_id}")

    zone_id = signal.get("zone_id")
    if zone_id:
        bits.append(f"zone {zone_id}")

    risk = signal.get("risk_score")
    if risk is not None:
        try:
            bits.append(f"risk {int(round(float(risk)))}")
        except (TypeError, ValueError):
            pass

    rec = signal.get("recommended_action")
    if rec:
        bits.append(f"action {rec}")

    return ", ".join(bits)


def build_cot_event(signal: dict[str, Any]) -> str:
    """Convert a wildfire_signal v1 record to a CoT XML event string.

    Returns a UTF-8 XML document (with the <?xml ...?> declaration) so it
    can be written to disk or sent over the wire as-is. Most TAK servers
    accept either form (with or without the declaration), but TAK Server
    log-replay prefers the declaration so we always emit it.
    """
    if not isinstance(signal, dict):
        raise TypeError("signal must be a dict (wildfire_signal v1 record)")

    signal_uuid = signal.get("signal_id") or str(uuid.uuid4())
    cot_type = cot_types.cot_type_for_signal(signal)
    emit_dt = _parse_signal_timestamp(signal.get("timestamp"))
    stale_dt = emit_dt + timedelta(seconds=cot_types.stale_seconds_for_signal(signal))
    lat, lon, hae = _select_point_coords(signal)
    ce = _select_ce(signal)
    le = _select_le(signal)

    event = ET.Element("event", attrib={
        "version": COT_VERSION,
        "uid": f"wfw-detection-{signal_uuid}",
        "type": cot_type,
        "how": COT_HOW_MACHINE_GPS,
        "time": _utc_iso(emit_dt),
        "start": _utc_iso(emit_dt),
        "stale": _utc_iso(stale_dt),
    })

    ET.SubElement(event, "point", attrib={
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "hae": f"{hae:.1f}",
        "ce": f"{ce:.1f}",
        "le": f"{le:.1f}",
    })

    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", attrib={"callsign": _build_callsign(signal)})

    remarks_text = _build_remarks(signal)
    if remarks_text:
        remarks_el = ET.SubElement(detail, "remarks")
        remarks_el.text = remarks_text

    ET.SubElement(detail, "__group", attrib={
        "name": COT_DEFAULT_GROUP_NAME,
        "role": COT_DEFAULT_GROUP_ROLE,
    })
    ET.SubElement(detail, "takv", attrib={
        "device": COT_EMITTER_DEVICE,
        "platform": COT_EMITTER_PLATFORM,
        "os": "python",
        "version": COT_EMITTER_VERSION,
    })
    ET.SubElement(detail, "_flow-tags_")

    drone_id = signal.get("drone_id")
    if drone_id:
        ET.SubElement(detail, "link", attrib={
            "uid": drone_id,
            "type": cot_types.DRONE_SELF_POSITION_COT_TYPE,
            "relation": "p-p",
        })

    ET.SubElement(detail, "archive")

    xml_bytes = ET.tostring(event, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def build_drone_self_position(
    drone_id: str,
    lat: float,
    lon: float,
    alt_msl_m: float = 0.0,
    *,
    callsign: str | None = None,
    ce_meters: float = COT_DEFAULT_CE_METERS,
    le_meters: float = COT_DEFAULT_LE_METERS,
    stale_seconds: int = 30,
    emit_dt: datetime | None = None,
) -> str:
    """Build a CoT self-position event for a drone.

    Self-position events are typically broadcast at ~1 Hz to UDP multicast
    239.2.3.1:6969 to populate the TAK situational-awareness map with the
    drone's own track.
    """
    emit_dt = emit_dt or datetime.now(UTC)
    stale_dt = emit_dt + timedelta(seconds=stale_seconds)
    cs = callsign or f"WFW-{drone_id.removeprefix('wfw-')}"

    event = ET.Element("event", attrib={
        "version": COT_VERSION,
        "uid": drone_id,
        "type": cot_types.DRONE_SELF_POSITION_COT_TYPE,
        "how": COT_HOW_MACHINE_GPS,
        "time": _utc_iso(emit_dt),
        "start": _utc_iso(emit_dt),
        "stale": _utc_iso(stale_dt),
    })
    ET.SubElement(event, "point", attrib={
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "hae": f"{float(alt_msl_m):.1f}",
        "ce": f"{ce_meters:.1f}",
        "le": f"{le_meters:.1f}",
    })
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", attrib={"callsign": cs[:24]})
    ET.SubElement(detail, "__group", attrib={
        "name": COT_DEFAULT_GROUP_NAME,
        "role": COT_DEFAULT_GROUP_ROLE,
    })
    ET.SubElement(detail, "takv", attrib={
        "device": COT_EMITTER_DEVICE,
        "platform": COT_EMITTER_PLATFORM,
        "os": "python",
        "version": COT_EMITTER_VERSION,
    })
    ET.SubElement(detail, "_flow-tags_")
    return ET.tostring(event, encoding="utf-8", xml_declaration=True).decode("utf-8")


def build_geofence_polygon(
    polygon_points: list[tuple[float, float]],
    *,
    name: str = "wfw-geofence",
    cot_uid: str | None = None,
    color_argb: int = 0x80FF00FF,  # semi-transparent magenta
    stale_seconds: int = 86400,
    emit_dt: datetime | None = None,
) -> str:
    """Build a CoT drawing event for a geofence polygon.

    ``polygon_points`` is a list of (lat, lon) tuples; the polygon is
    automatically closed (first point implicit at end) per CoT u-d-c-c
    convention.
    """
    if not polygon_points:
        raise ValueError("polygon_points must contain at least one (lat, lon)")

    emit_dt = emit_dt or datetime.now(UTC)
    stale_dt = emit_dt + timedelta(seconds=stale_seconds)
    uid = cot_uid or f"wfw-fence-{uuid.uuid4()}"

    centroid_lat = sum(p[0] for p in polygon_points) / len(polygon_points)
    centroid_lon = sum(p[1] for p in polygon_points) / len(polygon_points)

    event = ET.Element("event", attrib={
        "version": COT_VERSION,
        "uid": uid,
        "type": cot_types.GEOFENCE_POLYGON_COT_TYPE,
        "how": "h-e",  # human-entered (drawing)
        "time": _utc_iso(emit_dt),
        "start": _utc_iso(emit_dt),
        "stale": _utc_iso(stale_dt),
    })
    ET.SubElement(event, "point", attrib={
        "lat": f"{centroid_lat:.7f}",
        "lon": f"{centroid_lon:.7f}",
        "hae": "0.0",
        "ce": "9999999.0",
        "le": "9999999.0",
    })
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", attrib={"callsign": name[:24]})
    shape = ET.SubElement(detail, "shape")
    polyline = ET.SubElement(shape, "polyline", attrib={"closed": "true"})
    for lat, lon in polygon_points:
        ET.SubElement(polyline, "vertex", attrib={
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
            "hae": "0.0",
        })
    ET.SubElement(detail, "strokeColor").text = str(color_argb)
    ET.SubElement(detail, "strokeWeight").text = "3"
    ET.SubElement(detail, "fillColor").text = str(color_argb)
    ET.SubElement(detail, "remarks").text = f"wildfire-watch geofence: {name}"
    ET.SubElement(detail, "_flow-tags_")
    return ET.tostring(event, encoding="utf-8", xml_declaration=True).decode("utf-8")
