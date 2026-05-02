"""High-level emitter tests: signal -> XML mapping verifies attributes."""

from __future__ import annotations

import json
import socket
import threading
import time
from xml.etree import ElementTree as ET

import pytest

from sapphire_integration.tak.atak_emitter import emit
from sapphire_integration.tak.tak_server_client import TAKEndpoint


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


# --- signal -> XML attribute mapping ---


def test_smoke_signal_emits_b_r_f_h_s(smoke_signal):
    xml = emit(smoke_signal)
    root = _parse(xml)
    assert root.get("type") == "b-r-f-h-s"


def test_fire_signal_emits_b_r_f_h_c(fire_signal):
    xml = emit(fire_signal)
    root = _parse(xml)
    assert root.get("type") == "b-r-f-h-c"


def test_thermal_signal_emits_b_r_f_h_h(thermal_anomaly_signal):
    xml = emit(thermal_anomaly_signal)
    root = _parse(xml)
    assert root.get("type") == "b-r-f-h-h"


def test_wildlife_signal_emits_neutral_ground(wildlife_signal):
    xml = emit(wildlife_signal)
    root = _parse(xml)
    assert root.get("type") == "a-n-G"


def test_callsign_starts_with_wfw(smoke_signal):
    xml = emit(smoke_signal)
    cs = _parse(xml).find("detail/contact").get("callsign")
    assert cs.startswith("WFW-")


def test_remarks_contain_modalities(smoke_signal):
    xml = emit(smoke_signal)
    remarks = _parse(xml).find("detail/remarks").text or ""
    assert "0.92" in remarks
    assert "18.5" in remarks
    assert "wfw-unit01" in remarks


def test_target_coords_propagate(smoke_signal):
    xml = emit(smoke_signal)
    point = _parse(xml).find("point")
    assert float(point.get("lat")) == pytest.approx(38.9105, abs=1e-4)
    assert float(point.get("lon")) == pytest.approx(-107.0010, abs=1e-4)


def test_drone_coords_propagate_when_no_target(thermal_anomaly_signal):
    xml = emit(thermal_anomaly_signal)
    point = _parse(xml).find("point")
    assert float(point.get("lat")) == pytest.approx(38.91, abs=1e-4)
    assert float(point.get("lon")) == pytest.approx(-107.0, abs=1e-4)


# --- 10 different signal_types loop, all parse as well-formed XML ---


def test_serializes_many_signal_types_as_well_formed_xml(
    smoke_signal, fire_signal, thermal_anomaly_signal, wildlife_signal,
    anomaly_signal, system_event_signal, signal_minimal,
):
    signals = [
        smoke_signal,
        fire_signal,
        thermal_anomaly_signal,
        wildlife_signal,
        anomaly_signal,
        system_event_signal,
        signal_minimal,
        # variants pushing 10 in the loop
        {**smoke_signal, "confidence": 0.0},
        {**smoke_signal, "confidence": 1.0},
        {**smoke_signal, "drone_id": "wfw-unit42"},
    ]
    for sig in signals:
        xml = emit(sig)
        root = _parse(xml)
        assert root.tag == "event"
        assert root.find("point") is not None
        assert root.find("detail/contact").get("callsign")


# --- file output ---


def test_emit_writes_file(tmp_path, smoke_signal):
    out = tmp_path / "cot.xml"
    emit(smoke_signal, out=str(out))
    contents = out.read_text(encoding="utf-8")
    assert contents.startswith("<?xml")
    root = _parse(contents)
    assert root.tag == "event"


def test_emit_to_stdout_dash(smoke_signal, capsys):
    emit(smoke_signal, out="-")
    captured = capsys.readouterr().out
    assert "<event" in captured


# --- TAK endpoint URL parsing ---


def test_endpoint_parse_tcp():
    ep = TAKEndpoint.parse("tcp://atak.local:8087")
    assert ep.scheme == "tcp"
    assert ep.host == "atak.local"
    assert ep.port == 8087


def test_endpoint_parse_default_port():
    ep = TAKEndpoint.parse("tcp://atak.local")
    assert ep.port == 8087


def test_endpoint_parse_tak_alias():
    ep = TAKEndpoint.parse("tak://atak.local")
    assert ep.scheme == "tcp"
    assert ep.port == 8087


def test_endpoint_parse_mcast():
    ep = TAKEndpoint.parse("mcast://239.2.3.1:6969")
    assert ep.scheme == "mcast"
    assert ep.host == "239.2.3.1"
    assert ep.port == 6969


def test_endpoint_parse_bad_scheme():
    with pytest.raises(ValueError):
        TAKEndpoint.parse("ftp://x:1")


def test_endpoint_parse_no_scheme_defaults_tcp():
    ep = TAKEndpoint.parse("atak.local:8087")
    assert ep.scheme == "tcp"
    assert ep.host == "atak.local"


def test_endpoint_parse_missing_host():
    with pytest.raises(ValueError):
        TAKEndpoint.parse("tcp://")


# --- live TCP delivery against an in-process listener ---


def test_emit_over_tcp_to_local_listener(smoke_signal):
    received = []
    server_ready = threading.Event()

    def serve():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.listen(1)
            server_ready.set()
            serve.port = port  # type: ignore[attr-defined]
            conn, _ = s.accept()
            with conn:
                conn.settimeout(2.0)
                buf = bytearray()
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    buf.extend(chunk)
                received.append(bytes(buf))

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    server_ready.wait(timeout=2.0)
    # Tiny race window; spin briefly.
    for _ in range(20):
        if hasattr(serve, "port"):
            break
        time.sleep(0.01)
    port = serve.port  # type: ignore[attr-defined]

    emit(smoke_signal, server=f"tcp://127.0.0.1:{port}")
    t.join(timeout=5.0)

    assert received, "server received no bytes"
    payload = received[0].decode("utf-8")
    assert payload.startswith("<?xml")
    root = _parse(payload)
    assert root.get("type") == "b-r-f-h-s"
