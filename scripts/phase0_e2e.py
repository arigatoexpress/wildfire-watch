"""Phase 0 end-to-end harness.

Drives the full inference pipeline without the drone in hand:

    video file  +  flight-log CSV  +  fake webhook  ->  HMAC-signed POSTs
    -------------------------------------------------
        |          |                       |
        |          |                       v
        |          |          captured by an in-process HTTP server
        |          v
        |     MavicFlightLog.at(t)  ->  GpsFix  ->  build_signal(coords=...)
        v
    cv2.VideoCapture (lazy import; falls back to a synthetic frame stream
    if opencv is not installed)

The harness is intentionally lightweight: no opencv required, no
ultralytics, no real fire-detector model. It exercises the seams between
modules - flight-log GPS, geo projection, signal builder, HMAC webhook,
and on-disk retry queue - under stress conditions (intermittent webhook
outage, no-fix preamble, post-flight drain).

CLI:
    python3 scripts/phase0_e2e.py \
        --video    path/to/flight.mp4 \
        --log      path/to/flight.csv \
        --endpoint http://127.0.0.1:18080/ingest \
        --drone-id wfw-e2e01 \
        --zone-id  gunnison-corridor \
        [--fake-server]   # spin up an in-process echo server

This is what the test in tests/e2e/test_phase0_pipeline.py drives.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Make repo importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.fire_detection.geo import (  # noqa: E402
    BBox,
    Camera,
    DroneState,
    project_bbox_to_ground,
)
from ml.fire_detection.infer import (  # noqa: E402
    build_signal,
    drain_retry_queue,
    post_with_retry,
)
from ml.fire_detection.sources.mavic_log import (  # noqa: E402
    GpsFix,
    MavicFlightLog,
)

logger = logging.getLogger("wildfire_watch.phase0_e2e")


# ---------------------------------------------------------------------------
# Synthetic frame source - no opencv required.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeDetection:
    """A bbox + a confidence score, optionally with a forced thermal delta.

    The harness uses these to emulate the on-drone detector. Real flight
    data swaps this out for YOLOv8n + thermal capture.
    """

    bbox: BBox
    rgb_score: float
    thermal_delta_c: float


def synth_frame_stream(
    duration_s: float,
    fps: float = 30.0,
    detections_at: dict[float, FakeDetection] | None = None,
) -> Iterator[tuple[float, FakeDetection | None]]:
    """Yield (t_offset_s, detection_or_None) at `fps` for `duration_s`.

    `detections_at` keys are the wall-clock seconds at which a detection
    *fires*. We emit a detection for that frame and the surrounding
    persistence window so the fusion gate trips in the inference loop.
    """
    detections_at = detections_at or {}
    n = int(duration_s * fps)
    for i in range(n):
        t = i / fps
        # Find any detection within +/- 0.5s of this frame.
        det: FakeDetection | None = None
        for keyt, d in detections_at.items():
            if abs(keyt - t) <= 0.5:
                det = d
                break
        yield t, det


# ---------------------------------------------------------------------------
# Pipeline driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HarnessResult:
    """What the harness emitted. The e2e test asserts on this struct."""

    frames_processed: int
    detections_fired: int
    signals_posted: int
    signals_buffered: int
    final_buffer_remaining: int


def run_phase0_pipeline(
    *,
    flight_log: MavicFlightLog,
    frame_stream: Iterator[tuple[float, FakeDetection | None]],
    endpoint: str,
    secret: str,
    drone_id: str,
    zone_id: str,
    camera: Camera,
    retry_dir: Path,
    persistence_min: int = 5,
    confidence_threshold: float = 0.65,
    auto_loiter_threshold: float = 0.85,
) -> HarnessResult:
    """Run the full Phase-0 pipeline against a frame stream.

    Behaviour parity with `infer.py main()`:
      - Drains the retry queue at start.
      - For each frame, looks up GPS via `flight_log.at(t)`, runs the
        fusion gate, builds a v1 signal, and ships it through
        `post_with_retry` (HMAC + on-disk buffer).
      - Returns counts so the caller can assert on emitted vs buffered.
    """
    drained, _ = drain_retry_queue(endpoint, secret, retry_dir=retry_dir)
    if drained:
        logger.info("drained %d signals from retry queue", drained)

    frames = 0
    fired = 0
    posted = 0
    buffered = 0

    persistence_run = 0

    for t, det in frame_stream:
        frames += 1
        rgb_score = det.rgb_score if det else 0.0
        thermal_delta_c = det.thermal_delta_c if det else 0.0

        if rgb_score >= confidence_threshold:
            persistence_run += 1
        else:
            persistence_run = 0

        # Fusion gate (matches infer.should_emit).
        gate_open = (
            rgb_score >= confidence_threshold
            and thermal_delta_c >= 5.0
            and persistence_run >= persistence_min
        )
        if not (gate_open and det):
            continue

        # GPS for this frame from the flight log.
        fix: GpsFix | None = flight_log.at(t)
        if fix is None:
            logger.debug("no GPS fix at t=%.2f, skipping detection", t)
            continue

        # World-frame projection of the bbox center.
        drone_state = DroneState(
            lat=fix.lat,
            lon=fix.lon,
            alt_agl_m=max(fix.alt_agl_m, 1.0),
            yaw_deg=0.0,
            camera_pitch_deg=-30.0,
        )
        try:
            ground = project_bbox_to_ground(det.bbox, camera, drone_state)
            target_coords = {"lat": ground.lat, "lon": ground.lon}
        except ValueError:
            target_coords = None  # ray pointed above horizon - log only

        confidence = min(
            1.0,
            0.5 * rgb_score + 0.5 * min(thermal_delta_c / 30.0, 1.0),
        )
        signal_type = "fire" if thermal_delta_c >= 15.0 else "smoke"
        recommended = (
            "loiter_and_capture"
            if confidence >= auto_loiter_threshold
            else "notify_operator"
        )

        sig = build_signal(
            drone_id=drone_id,
            zone_id=zone_id,
            coords=fix.to_coords(),
            target_coords=target_coords,
            signal_type=signal_type,
            confidence=confidence,
            rgb_yolo_score=rgb_score,
            thermal_delta_c=thermal_delta_c,
            frame_uris=[f"phase0://frame_{frames:06d}.jpg"],
            risk_score=confidence * 100.0,
            recommended_action=recommended,
        )
        fired += 1
        ok = post_with_retry(endpoint, sig, secret=secret, retry_dir=retry_dir)
        if ok:
            posted += 1
        else:
            buffered += 1

    final_remaining = (
        len(list(retry_dir.glob("*.json"))) if retry_dir.exists() else 0
    )
    return HarnessResult(
        frames_processed=frames,
        detections_fired=fired,
        signals_posted=posted,
        signals_buffered=buffered,
        final_buffer_remaining=final_remaining,
    )


# ---------------------------------------------------------------------------
# CLI entry - only invoked when a real video file is supplied.
# ---------------------------------------------------------------------------


def _cv2_frame_stream(
    video_path: Path,
    fake_detection_at: dict[float, FakeDetection] | None = None,
) -> Iterator[tuple[float, FakeDetection | None]]:
    """Open a video file with opencv-python-headless and yield frames.

    We don't actually run a model on the pixels - this is the harness, so
    detections are scripted via `fake_detection_at`. A real run swaps this
    function for an inference-bound iterator.
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised by CLI only
        raise RuntimeError(
            "opencv-python-headless is required for --video mode; "
            "install with `pip install -e \".[ml]\"`"
        ) from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {video_path!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    fake_detection_at = fake_detection_at or {}
    try:
        i = 0
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            t = i / fps
            det: FakeDetection | None = None
            for keyt, d in fake_detection_at.items():
                if abs(keyt - t) <= 0.5:
                    det = d
                    break
            yield t, det
            i += 1
    finally:
        cap.release()


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, default=None,
                   help="MP4/MOV file. If omitted, a synthetic frame stream "
                        "is used (no opencv required).")
    p.add_argument("--log", type=Path, required=True,
                   help="Mavic flight-log CSV.")
    p.add_argument("--endpoint", required=True)
    p.add_argument("--drone-id", required=True)
    p.add_argument("--zone-id", required=True)
    p.add_argument("--secret", default=os.environ.get("WILDFIRE_WEBHOOK_SECRET", ""))
    p.add_argument("--retry-dir", type=Path,
                   default=Path.home() / ".wildfire" / "retry")
    p.add_argument("--duration-s", type=float, default=10.0,
                   help="Synthetic frame stream duration (when --video omitted).")
    p.add_argument("--fake-server", action="store_true",
                   help="Spin up an in-process HTTP server that 200s every "
                        "POST. Useful for a stand-alone smoke run.")
    return p


def main() -> int:
    args = _build_argparser().parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if not args.secret:
        logger.error("WILDFIRE_WEBHOOK_SECRET (or --secret) must be set")
        return 2

    log = MavicFlightLog(args.log)
    if not log.fixes():
        logger.error("flight log has no GPS fixes after parsing: %s", args.log)
        return 2

    server = None
    endpoint = args.endpoint
    if args.fake_server:
        server, endpoint = _start_fake_server()

    # A bbox in the lower-center of a 1920x1080 frame -> projects forward
    # and down once the camera pitch is applied.
    detection = FakeDetection(
        bbox=BBox(900, 700, 1020, 820),
        rgb_score=0.92,
        thermal_delta_c=22.0,
    )
    # Fire one detection 1s after the second flight-log fix.
    fire_at = (log.fixes()[1].t_offset_s + 1.0) if len(log) > 1 else 1.0

    if args.video and args.video.exists():
        stream = _cv2_frame_stream(args.video, {fire_at: detection})
    else:
        stream = synth_frame_stream(
            args.duration_s,
            detections_at={fire_at: detection},
        )

    camera = Camera(
        horizontal_fov_deg=83.0,
        vertical_fov_deg=47.0,
        image_width_px=1920,
        image_height_px=1080,
    )
    result = run_phase0_pipeline(
        flight_log=log,
        frame_stream=stream,
        endpoint=endpoint,
        secret=args.secret,
        drone_id=args.drone_id,
        zone_id=args.zone_id,
        camera=camera,
        retry_dir=args.retry_dir,
    )
    print(json.dumps(result.__dict__, indent=2))

    if server is not None:
        server.shutdown()
    return 0


# ---------------------------------------------------------------------------
# In-process echo server (for the CLI --fake-server convenience).
# Tests hit it via wsgiref directly; this CLI helper is for humans.
# ---------------------------------------------------------------------------


def _start_fake_server() -> tuple[object, str]:  # pragma: no cover - CLI helper
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server signature
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *_args, **_kwargs):  # noqa: D401 - silence stderr noise
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}/ingest"


if __name__ == "__main__":
    sys.exit(main())
