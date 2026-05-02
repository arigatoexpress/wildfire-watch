"""Phase 0 end-to-end pipeline test.

Exercises the seam between every Phase-0 module:

  scripts/phase0_e2e.run_phase0_pipeline()
        |
        +- ml.fire_detection.sources.mavic_log.MavicFlightLog  (#3)
        +- ml.fire_detection.geo.project_bbox_to_ground         (#4)
        +- ml.fire_detection.infer.build_signal                 (existing)
        +- ml.fire_detection.infer.post_with_retry              (#2)

Three scenarios:
  1. happy path  : flight log + synth frames + 200 server -> N posts, 0 buffer
  2. webhook out : same input, server returns 502 -> 0 posts, N buffered
  3. drain       : fixture seeds buffer, server returns 200 -> drain on start

Run:
    cd ~/Code/wildfire-watch
    python3 -m pytest tests/e2e -q
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

# Make scripts/ + repo importable.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from phase0_e2e import (  # noqa: E402
    BBox,
    Camera,
    FakeDetection,
    HarnessResult,
    run_phase0_pipeline,
    synth_frame_stream,
)
from ml.fire_detection.infer import buffer_signal, build_signal  # noqa: E402
from ml.fire_detection.sources.mavic_log import MavicFlightLog  # noqa: E402


# ---------------------------------------------------------------------------
# In-process HTTP server. Each test gets its own port (port=0 -> ephemeral).
# ---------------------------------------------------------------------------


class _RecordingHandler(BaseHTTPRequestHandler):
    """A plain handler that captures every POST body + headers and responds
    according to the server's `_status` attribute."""

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.captured.append(  # type: ignore[attr-defined]
            {
                "headers": {k: v for k, v in self.headers.items()},
                "body": body,
            }
        )
        status = self.server._status  # type: ignore[attr-defined]
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b'{"ok":true}' if status == 200 else b'{"err":true}')

    def log_message(self, *args, **kwargs):  # noqa: D401
        return  # silence stderr noise during tests


def _start_recording_server(status: int = 200) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.captured = []  # type: ignore[attr-defined]
    server._status = status  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}/ingest"
    return server, endpoint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_flight_log(tmp_path: Path) -> MavicFlightLog:
    csv_text = (
        "ts,lat,lon,alt_agl_m\n"
        "0.00,38.8200,-106.9870,0.0\n"
        "0.50,38.8200,-106.9870,5.0\n"
        "1.00,38.8201,-106.9869,15.0\n"
        "1.50,38.8202,-106.9868,40.0\n"
        "2.00,38.8203,-106.9867,80.0\n"
        "3.00,38.8204,-106.9866,100.0\n"
        "5.00,38.8205,-106.9865,100.0\n"
        "8.00,38.8206,-106.9864,100.0\n"
    )
    log_path = tmp_path / "flight.csv"
    log_path.write_text(csv_text)
    return MavicFlightLog(log_path)


@pytest.fixture
def camera() -> Camera:
    return Camera(83.0, 47.0, 1920, 1080)


def _frames_with_fire_window(fire_at: float):
    """A 6 s synth stream where a confident detection fires for 1 s
    around `fire_at` - long enough to clear persistence_min=5 at 30 fps.
    """
    detection = FakeDetection(
        bbox=BBox(900, 700, 1020, 820),
        rgb_score=0.92,
        thermal_delta_c=22.0,
    )
    # Make detection cover [fire_at-0.5, fire_at+0.5]; synth_frame_stream
    # already ramps detections within +/- 0.5 s of the key.
    return synth_frame_stream(
        duration_s=6.0,
        fps=30.0,
        detections_at={fire_at: detection},
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_phase0_happy_path_posts_signed_signal(
    tmp_path: Path,
    synthetic_flight_log: MavicFlightLog,
    camera: Camera,
) -> None:
    server, endpoint = _start_recording_server(status=200)
    try:
        result = run_phase0_pipeline(
            flight_log=synthetic_flight_log,
            frame_stream=_frames_with_fire_window(fire_at=3.0),
            endpoint=endpoint,
            secret="topsecret",
            drone_id="wfw-e2e01",
            zone_id="gunnison-corridor",
            camera=camera,
            retry_dir=tmp_path / "retry",
        )
    finally:
        server.shutdown()

    assert isinstance(result, HarnessResult)
    assert result.frames_processed > 0
    assert result.detections_fired > 0
    assert result.signals_posted == result.detections_fired
    assert result.signals_buffered == 0
    assert result.final_buffer_remaining == 0

    # At least one signal hit the server, and it carried HMAC headers.
    assert len(server.captured) >= 1  # type: ignore[attr-defined]
    sample = server.captured[0]  # type: ignore[attr-defined]
    assert "X-Wildfire-Signature" in sample["headers"]
    assert "X-Wildfire-Timestamp" in sample["headers"]
    body = json.loads(sample["body"])
    assert body["drone_id"] == "wfw-e2e01"
    assert body["zone_id"] == "gunnison-corridor"
    assert body["schema_version"] == "1.0.0"
    assert "coords" in body and "lat" in body["coords"]
    # target_coords should be populated - bbox lower-center + pitch -30
    # projects forward onto the ground plane.
    assert body["target_coords"] is not None
    assert "lat" in body["target_coords"]


# ---------------------------------------------------------------------------
# Webhook outage -> retry buffer
# ---------------------------------------------------------------------------


def test_phase0_webhook_502_buffers_to_disk(
    tmp_path: Path,
    synthetic_flight_log: MavicFlightLog,
    camera: Camera,
) -> None:
    server, endpoint = _start_recording_server(status=502)
    try:
        result = run_phase0_pipeline(
            flight_log=synthetic_flight_log,
            frame_stream=_frames_with_fire_window(fire_at=3.0),
            endpoint=endpoint,
            secret="topsecret",
            drone_id="wfw-e2e01",
            zone_id="gunnison-corridor",
            camera=camera,
            retry_dir=tmp_path / "retry",
        )
    finally:
        server.shutdown()

    assert result.detections_fired > 0
    assert result.signals_posted == 0
    assert result.signals_buffered == result.detections_fired
    # Every fired signal lands as a JSON file in the retry dir.
    pending = list((tmp_path / "retry").glob("*.json"))
    assert len(pending) == result.signals_buffered


# ---------------------------------------------------------------------------
# Drain on start
# ---------------------------------------------------------------------------


def test_phase0_drains_preexisting_buffer_on_start(
    tmp_path: Path,
    synthetic_flight_log: MavicFlightLog,
    camera: Camera,
) -> None:
    """Seed the retry dir with one signal from a 'previous flight', then
    run the pipeline against a 200-OK server. The seeded signal should
    drain at startup before any new signals fire."""
    retry = tmp_path / "retry"
    seeded = build_signal(
        drone_id="wfw-e2e01",
        zone_id="gunnison-corridor",
        coords={"lat": 38.5, "lon": -106.9, "alt_agl_m": 90.0},
        target_coords=None,
        signal_type="smoke",
        confidence=0.91,
        rgb_yolo_score=0.93,
        thermal_delta_c=18.5,
        frame_uris=["phase0://seeded.jpg"],
        risk_score=78.0,
        recommended_action="notify_operator",
    )
    buffer_signal(seeded, retry_dir=retry)
    assert len(list(retry.glob("*.json"))) == 1

    server, endpoint = _start_recording_server(status=200)
    try:
        result = run_phase0_pipeline(
            flight_log=synthetic_flight_log,
            # No new detections: empty detections_at dict.
            frame_stream=synth_frame_stream(duration_s=2.0, detections_at={}),
            endpoint=endpoint,
            secret="topsecret",
            drone_id="wfw-e2e01",
            zone_id="gunnison-corridor",
            camera=camera,
            retry_dir=retry,
        )
    finally:
        server.shutdown()

    # No new signals fired this run.
    assert result.detections_fired == 0
    # But the seeded signal must have drained.
    assert result.final_buffer_remaining == 0
    assert len(list(retry.glob("*.json"))) == 0
    # Server saw the seeded signal.
    assert len(server.captured) == 1  # type: ignore[attr-defined]
    body = json.loads(server.captured[0]["body"])  # type: ignore[attr-defined]
    assert body["signal_id"] == seeded["signal_id"]
