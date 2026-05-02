"""Round-trip tests: build_cot_event(signal) -> well-formed CoT XML."""

from __future__ import annotations

from datetime import UTC, datetime
from xml.etree import ElementTree as ET

import pytest

from sapphire_integration.tak.cot_event import (
    build_cot_event,
    build_drone_self_position,
    build_geofence_polygon,
)


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


# --- xml shape ---


def test_smoke_signal_produces_well_formed_xml(smoke_signal):
    xml = build_cot_event(smoke_signal)
    root = _parse(xml)
    assert root.tag == "event"
    # All required CoT 2.0 attributes present.
    for attr in ("version", "uid", "type", "how", "time", "start", "stale"):
        assert root.get(attr), f"missing event/@{attr}"
    assert root.get("version") == "2.0"
    assert root.get("how") == "m-g"
    assert root.get("uid").startswith("wfw-detection-")


def test_event_has_xml_declaration(smoke_signal):
    xml = build_cot_event(smoke_signal)
    assert xml.startswith("<?xml")
    assert "encoding=" in xml.lower()


def test_event_point_has_required_attrs(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    point = root.find("point")
    assert point is not None
    for attr in ("lat", "lon", "hae", "ce", "le"):
        assert point.get(attr) is not None, f"missing point/@{attr}"


def test_event_detail_has_contact_takv_group(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    detail = root.find("detail")
    assert detail is not None
    assert detail.find("contact") is not None
    assert detail.find("takv") is not None
    assert detail.find("__group") is not None
    assert detail.find("_flow-tags_") is not None
    assert detail.find("archive") is not None


def test_target_coords_used_when_present(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    point = root.find("point")
    target = smoke_signal["target_coords"]
    assert float(point.get("lat")) == pytest.approx(target["lat"], abs=1e-6)
    assert float(point.get("lon")) == pytest.approx(target["lon"], abs=1e-6)


def test_drone_coords_used_when_no_target(thermal_anomaly_signal):
    root = _parse(build_cot_event(thermal_anomaly_signal))
    point = root.find("point")
    coords = thermal_anomaly_signal["coords"]
    assert float(point.get("lat")) == pytest.approx(coords["lat"], abs=1e-6)
    assert float(point.get("lon")) == pytest.approx(coords["lon"], abs=1e-6)


def test_ce_pulled_from_target_uncertainty(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    point = root.find("point")
    assert float(point.get("ce")) == pytest.approx(18.0, abs=1e-6)


def test_ce_falls_back_to_default(thermal_anomaly_signal):
    root = _parse(build_cot_event(thermal_anomaly_signal))
    point = root.find("point")
    assert float(point.get("ce")) == pytest.approx(25.0, abs=1e-6)


# --- timestamps ---


def test_stale_window_smoke_is_one_hour(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    t0 = datetime.fromisoformat(root.get("time").replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(root.get("stale").replace("Z", "+00:00"))
    assert (t1 - t0).total_seconds() == pytest.approx(3600, abs=1)


def test_stale_window_thermal_anomaly_is_15_min(thermal_anomaly_signal):
    root = _parse(build_cot_event(thermal_anomaly_signal))
    t0 = datetime.fromisoformat(root.get("time").replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(root.get("stale").replace("Z", "+00:00"))
    assert (t1 - t0).total_seconds() == pytest.approx(900, abs=1)


def test_emit_time_matches_signal_timestamp(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    assert root.get("time") == "2026-05-02T20:14:00Z"
    assert root.get("start") == "2026-05-02T20:14:00Z"


def test_bad_timestamp_falls_back_to_now(smoke_signal):
    smoke_signal["timestamp"] = "not-a-real-timestamp"
    root = _parse(build_cot_event(smoke_signal))
    parsed = datetime.fromisoformat(root.get("time").replace("Z", "+00:00"))
    delta = abs((datetime.now(UTC) - parsed).total_seconds())
    assert delta < 60, f"emit time should be ~now, got delta {delta}s"


# --- detail children ---


def test_remarks_contain_rgb_and_thermal_numbers(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    remarks = root.find("detail/remarks")
    assert remarks is not None
    text = remarks.text or ""
    assert "0.92" in text  # rgb_yolo_score
    assert "18.5" in text  # thermal_delta_c
    assert "wfw-unit01" in text
    assert "slate-river-drainage" in text


def test_link_to_drone_is_present(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    link = root.find("detail/link")
    assert link is not None
    assert link.get("uid") == "wfw-unit01"
    assert link.get("relation") == "p-p"


def test_callsign_under_24_chars(smoke_signal):
    root = _parse(build_cot_event(smoke_signal))
    cs = root.find("detail/contact").get("callsign")
    assert len(cs) <= 24
    assert cs.startswith("WFW-")


def test_callsign_truncates_long_subtype(smoke_signal):
    smoke_signal["signal_subtype"] = "smoke/very_long_subtype_that_overflows"
    root = _parse(build_cot_event(smoke_signal))
    cs = root.find("detail/contact").get("callsign")
    assert len(cs) <= 24
    assert cs.startswith("WFW-")


# --- minimal / corner cases ---


def test_minimal_signal_still_builds(signal_minimal):
    xml = build_cot_event(signal_minimal)
    root = _parse(xml)
    assert root.find("point") is not None
    assert root.find("detail/contact") is not None


def test_non_dict_input_raises():
    with pytest.raises(TypeError):
        build_cot_event("not a dict")  # type: ignore[arg-type]


# --- self-position ---


def test_self_position_xml_well_formed():
    xml = build_drone_self_position("wfw-unit01", 38.91, -107.0, 80.0)
    root = _parse(xml)
    assert root.tag == "event"
    assert root.get("uid") == "wfw-unit01"
    assert root.get("type").startswith("a-f-A-M-F-Q")
    point = root.find("point")
    assert float(point.get("lat")) == pytest.approx(38.91, abs=1e-6)
    assert root.find("detail/contact").get("callsign").startswith("WFW-")


def test_self_position_default_stale_is_30s():
    xml = build_drone_self_position("wfw-unit01", 38.91, -107.0)
    root = _parse(xml)
    t0 = datetime.fromisoformat(root.get("time").replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(root.get("stale").replace("Z", "+00:00"))
    assert (t1 - t0).total_seconds() == pytest.approx(30, abs=1)


# --- geofence ---


def test_geofence_polygon_well_formed():
    poly = [
        (38.9100, -107.0000),
        (38.9100, -106.9900),
        (38.9000, -106.9900),
        (38.9000, -107.0000),
    ]
    xml = build_geofence_polygon(poly, name="slate-river")
    root = _parse(xml)
    assert root.tag == "event"
    assert root.get("type") == "u-d-c-c"
    polyline = root.find("detail/shape/polyline")
    assert polyline is not None
    assert polyline.get("closed") == "true"
    verts = polyline.findall("vertex")
    assert len(verts) == 4
    assert root.find("detail/contact").get("callsign") == "slate-river"


def test_geofence_empty_polygon_raises():
    with pytest.raises(ValueError):
        build_geofence_polygon([], name="empty")
