"""wildfire-watch — on-drone fire/smoke inference loop.

Skeleton:
- Reads RGB (MIPI-CSI) + thermal (USB UVC from PureThermal 3) frames.
- Runs YOLOv8n TensorRT engine.
- Cross-checks against thermal delta-T.
- On positive: assembles a wildfire_signal (see sapphire_integration/wildfire_signal_schema.json),
  POSTs to ground station, optionally loiters via MAVLink COMMAND_LONG.

This file is intentionally a skeleton with the signal-emit shape locked in.
Camera capture + TensorRT engine wiring is filled in once hardware is in hand.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("wildfire_watch.infer")

SCHEMA_VERSION = "1.0.0"

# Default on-disk retry directory. Each undeliverable signal lands here as
# `<unix_ts>-<signal_id>.json`; drained on the next process boot or by an
# explicit drain_retry_queue() call.
DEFAULT_RETRY_DIR = Path.home() / ".wildfire" / "retry"

# HMAC body header — receivers compute HMAC-SHA256 over the raw JSON bytes
# using the shared secret and compare against this header. The Bearer
# header still ships for legacy receivers but is being deprecated.
HMAC_HEADER = "X-Wildfire-Signature"
HMAC_TIMESTAMP_HEADER = "X-Wildfire-Timestamp"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch on-drone inference.")
    p.add_argument("--engine", required=True, help="Path to TensorRT engine.")
    p.add_argument("--rgb_device", default="/dev/video0")
    p.add_argument("--thermal_device", default="/dev/video1")
    p.add_argument("--mavlink_url", default="udp:127.0.0.1:14550")
    p.add_argument("--signal_endpoint", required=True,
                   help="Ground station URL accepting wildfire_signal POSTs.")
    p.add_argument("--drone_id", required=True)
    p.add_argument("--zone_id", required=True)
    p.add_argument("--confidence_threshold", type=float, default=0.65)
    p.add_argument("--auto_loiter_threshold", type=float, default=0.85)
    p.add_argument("--persistence_frames", type=int, default=5)
    # Phase-0 GPS source: a Mavic-Mini flight-log CSV. When set, the
    # inference loop pulls coords from this file instead of MAVLink.
    # See ml/fire_detection/sources/mavic_log.py.
    p.add_argument(
        "--mavic_log",
        default=None,
        help="Path to a Mavic Mini flight-log CSV (DJI Fly / Airdata / "
             "DatCon). When set, GPS comes from this file instead of MAVLink.",
    )
    return p.parse_args()


def should_emit(
    rgb_score: float,
    thermal_delta_c: float,
    persistence_frames: int,
    geofence_ok: bool,
    wind_consistent: bool,
    threshold: float,
    persistence_min: int,
) -> bool:
    """Multimodal fusion gate. See docs/30-ml-stack.md."""
    return (
        rgb_score >= threshold
        and thermal_delta_c >= 5.0
        and persistence_frames >= persistence_min
        and geofence_ok
        and wind_consistent
    )


def build_signal(
    *,
    drone_id: str,
    zone_id: str,
    coords: dict[str, float],
    target_coords: dict[str, float] | None,
    signal_type: str,
    confidence: float,
    rgb_yolo_score: float,
    thermal_delta_c: float,
    frame_uris: list[str],
    risk_score: float,
    recommended_action: str,
) -> dict[str, Any]:
    """Construct a wildfire_signal v1.0.0 conforming to the schema."""
    return {
        "schema_version": SCHEMA_VERSION,
        "signal_id": str(uuid.uuid4()),
        "drone_id": drone_id,
        "zone_id": zone_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "coords": coords,
        "target_coords": target_coords,
        "signal_type": signal_type,
        "confidence": confidence,
        "evidence": {
            "frame_uris": frame_uris,
            "model_outputs": {
                "rgb_yolo_score": rgb_yolo_score,
                "thermal_delta_c": thermal_delta_c,
            },
        },
        "risk_score": risk_score,
        "recommended_action": recommended_action,
        "geofence_status": {
            "in_authorized_zone": True,
            "tfr_active": False,
            "remote_id_active": True,
        },
    }


def _sign_body(body: bytes, secret: str, timestamp: str) -> str:
    """HMAC-SHA256(secret, timestamp + "." + body) -> hex digest.

    Including the timestamp in the signed payload defeats simple replays
    of stale captured signals. Receivers reject signatures whose timestamp
    is more than ~5 minutes off wall clock.
    """
    mac = hmac.new(
        secret.encode("utf-8"),
        msg=timestamp.encode("ascii") + b"." + body,
        digestmod=hashlib.sha256,
    )
    return mac.hexdigest()


def post_signal(
    endpoint: str,
    signal: dict[str, Any],
    secret: str,
    *,
    timeout: float = 5.0,
) -> None:
    """POST signal to ground station / Sapphire signal_logger.

    Headers shipped:
      Authorization              Bearer <secret>            (legacy)
      X-Wildfire-Signature       hex(HMAC-SHA256(secret, ts.body))
      X-Wildfire-Timestamp       unix seconds (string)

    Receivers MUST verify X-Wildfire-Signature; the Bearer header is kept
    for backward compatibility with the early signal_logger and will be
    removed once Sapphire's signal_logger ships HMAC verification.

    Raises requests.HTTPError on non-2xx so the caller can route to the
    on-disk retry queue.
    """
    import requests  # noqa: PLC0415  (lazy import — see module docstring)

    body = json.dumps(signal, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    sig = _sign_body(body, secret, ts)

    r = requests.post(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
            HMAC_HEADER: sig,
            HMAC_TIMESTAMP_HEADER: ts,
        },
        timeout=timeout,
    )
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Retry queue — survives a power-cycle on the drone or ground station.
# ---------------------------------------------------------------------------


def _retry_path(signal: dict[str, Any], retry_dir: Path) -> Path:
    """Stable per-signal filename: `<unix_ts>-<signal_id>.json`.

    Sorting the directory lexically yields chronological order because the
    UNIX-timestamp prefix is fixed-width-ish for the next ~270 years.
    """
    sid = signal.get("signal_id", str(uuid.uuid4()))
    ts = int(time.time())
    return retry_dir / f"{ts}-{sid}.json"


def buffer_signal(signal: dict[str, Any], retry_dir: Path = DEFAULT_RETRY_DIR) -> Path:
    """Persist a signal to the on-disk retry queue.

    Returns the path written so callers / tests can assert on it.
    """
    retry_dir.mkdir(parents=True, exist_ok=True)
    path = _retry_path(signal, retry_dir)
    # Write atomically: tmp + rename so a torn write can't leave half a JSON.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(signal, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path


def drain_retry_queue(
    endpoint: str,
    secret: str,
    retry_dir: Path = DEFAULT_RETRY_DIR,
    *,
    max_per_call: int = 64,
) -> tuple[int, int]:
    """Replay buffered signals from `retry_dir` to `endpoint`.

    Returns (drained, remaining). Drained signals are unlinked. The first
    delivery failure stops the drain — we don't want to bury a fresh
    incident under stale buffered traffic.
    """
    if not retry_dir.exists():
        return (0, 0)

    pending = sorted(retry_dir.glob("*.json"))
    drained = 0
    for path in pending[:max_per_call]:
        try:
            sig = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("retry: dropping malformed %s: %s", path.name, exc)
            path.unlink(missing_ok=True)
            continue
        try:
            post_signal(endpoint, sig, secret=secret)
        except Exception as exc:  # noqa: BLE001 — retry queue tolerates anything
            logger.info("retry: still failing on %s: %s", path.name, exc)
            break
        path.unlink(missing_ok=True)
        drained += 1

    remaining = len(list(retry_dir.glob("*.json")))
    return (drained, remaining)


def post_with_retry(
    endpoint: str,
    signal: dict[str, Any],
    secret: str,
    retry_dir: Path = DEFAULT_RETRY_DIR,
) -> bool:
    """Best-effort post; on failure, persist to retry_dir.

    Returns True on success, False if the signal was buffered.
    """
    try:
        post_signal(endpoint, signal, secret=secret)
        return True
    except Exception as exc:  # noqa: BLE001 — every send failure mode is buffered
        path = buffer_signal(signal, retry_dir=retry_dir)
        logger.warning("post failed (%s); buffered to %s", exc, path)
        return False


# ---------------------------------------------------------------------------
# Evidence upload — bridge to ml/fire_detection/evidence.py
# ---------------------------------------------------------------------------


def _import_evidence():
    """Import the evidence module under either invocation style.

    ``infer.py`` is imported as ``from infer import ...`` (sys.path
    injection in tests + `mavic_post_flight.py` + `sim/swarm/fleet.py`)
    AND as ``from ml.fire_detection.infer import ...`` (the e2e tests
    + ``scripts/phase0_e2e.py``). Pick whichever resolves first.
    """
    try:
        from ml.fire_detection import evidence as _e  # noqa: PLC0415
        return _e
    except ImportError:
        import evidence as _e  # type: ignore[no-redef]  # noqa: PLC0415, I001
        return _e


def upload_evidence_frames(
    frames: list[tuple[bytes, str]],
    flight_id: str,
    *,
    bucket: str | None = None,
    signed_url_expires_in: int | None = None,
) -> tuple[list[str], list[str]]:
    """Upload a list of ``(jpeg_bytes, frame_id)`` tuples to GCS.

    Returns ``(frame_uris, signed_urls)``. ``frame_uris`` is always
    populated (one per input, even on retry-buffer fallback) so the
    signal carries a stable identifier even when the bucket is
    unreachable. ``signed_urls`` is empty unless
    ``signed_url_expires_in`` was passed AND every upload reached GCS.

    Designed to be called from the inference loop right before
    ``build_signal``, so the resulting URIs flow into the signal's
    ``evidence.frame_uris`` array.
    """
    ev = _import_evidence()
    uris: list[str] = []
    signed: list[str] = []
    for frame_bytes, frame_id in frames:
        result = ev.upload_frame(
            frame_bytes,
            flight_id=flight_id,
            frame_id=frame_id,
            bucket=bucket,
            signed_url_expires_in=signed_url_expires_in,
        )
        uris.append(result.uri)
        if result.signed_url:
            signed.append(result.signed_url)
    return uris, signed


def _resolve_secret() -> str:
    """Read the webhook secret from $WILDFIRE_WEBHOOK_SECRET.

    Refuses to start with the placeholder so a misconfigured drone can't
    accidentally ship signed-with-`REPLACE_ME` traffic into production.
    """
    secret = os.environ.get("WILDFIRE_WEBHOOK_SECRET", "")
    if not secret or secret == "REPLACE_ME":
        raise RuntimeError(
            "WILDFIRE_WEBHOOK_SECRET env var must be set to a non-empty, "
            "non-placeholder value before running the inference loop."
        )
    return secret


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # TODO(camera): open MIPI-CSI RGB capture (Arducam IMX477) via gstreamer pipeline.
    # TODO(thermal): open UVC thermal capture (PureThermal 3) via v4l2.
    # TODO(engine): load TensorRT engine, prepare CUDA context.
    # TODO(mavlink): pymavlink connection to UDP 14550, subscribe to GLOBAL_POSITION_INT.

    secret = _resolve_secret()

    # Drain any signals buffered during the previous flight before going live.
    try:
        drained, remaining = drain_retry_queue(args.signal_endpoint, secret)
        if drained or remaining:
            logger.info("retry queue: drained %d, remaining %d", drained, remaining)
    except Exception as exc:  # noqa: BLE001
        logger.warning("retry-queue drain skipped: %s", exc)

    # Drain any evidence frames buffered when GCS was unreachable last flight.
    try:
        ev = _import_evidence()
        ev_drained, ev_remaining = ev.drain_evidence_queue()
        if ev_drained or ev_remaining:
            logger.info(
                "evidence retry queue: drained %d, remaining %d",
                ev_drained,
                ev_remaining,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("evidence-queue drain skipped: %s", exc)

    persistence = deque(maxlen=args.persistence_frames)
    logger.info("wildfire-watch infer loop starting; engine=%s", args.engine)

    flight_id = f"{args.drone_id}-{int(time.time())}"
    while True:
        # Skeleton — replace with real capture + inference.
        rgb_score = 0.0
        thermal_delta_c = 0.0
        coords = {"lat": 0.0, "lon": 0.0, "alt_agl_m": 0.0}
        geofence_ok = True
        wind_consistent = True
        # Captured detection frames (jpeg bytes + per-frame id). Real
        # capture loop fills this; the skeleton emits an empty list which
        # short-circuits to a no-op upload.
        detection_frames: list[tuple[bytes, str]] = []

        persistence.append(rgb_score >= args.confidence_threshold)
        run_length = sum(persistence)

        if should_emit(
            rgb_score=rgb_score,
            thermal_delta_c=thermal_delta_c,
            persistence_frames=run_length,
            geofence_ok=geofence_ok,
            wind_consistent=wind_consistent,
            threshold=args.confidence_threshold,
            persistence_min=args.persistence_frames,
        ):
            confidence = min(1.0, 0.5 * rgb_score + 0.5 * min(thermal_delta_c / 30.0, 1.0))
            signal_type = "fire" if thermal_delta_c >= 15.0 else "smoke"
            recommended = (
                "loiter_and_capture"
                if confidence >= args.auto_loiter_threshold
                else "notify_operator"
            )
            # GCS evidence upload — closes the TODO(evidence) line. Empty
            # detection_frames yields an empty URI list, which is fine for
            # the skeleton; once camera capture is wired, every emit ships
            # frames straight to GCS.
            frame_uris: list[str] = []
            if detection_frames:
                try:
                    frame_uris, _signed = upload_evidence_frames(
                        detection_frames,
                        flight_id=flight_id,
                        signed_url_expires_in=3600,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("evidence upload skipped: %s", exc)
            sig = build_signal(
                drone_id=args.drone_id,
                zone_id=args.zone_id,
                coords=coords,
                target_coords=None,  # TODO(geo): pixel_to_geo()
                signal_type=signal_type,
                confidence=confidence,
                rgb_yolo_score=rgb_score,
                thermal_delta_c=thermal_delta_c,
                frame_uris=frame_uris,
                risk_score=confidence * 100.0,
                recommended_action=recommended,
            )
            # post_with_retry handles its own logging + on-disk buffering.
            post_with_retry(args.signal_endpoint, sig, secret=secret)

            print(json.dumps(sig, indent=2))

        time.sleep(1.0 / 30.0)  # ~30 Hz capture loop placeholder


if __name__ == "__main__":
    main()
