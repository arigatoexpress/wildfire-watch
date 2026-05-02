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
import json
import logging
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("wildfire_watch.infer")

SCHEMA_VERSION = "1.0.0"


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


def post_signal(endpoint: str, signal: dict[str, Any], secret: str) -> None:
    """POST signal to ground station / Sapphire signal_logger.

    Lazy import requests so test discovery works without it installed.
    """
    import requests  # noqa: PLC0415

    r = requests.post(
        endpoint,
        json=signal,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=5.0,
    )
    r.raise_for_status()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # TODO(camera): open MIPI-CSI RGB capture (Arducam IMX477) via gstreamer pipeline.
    # TODO(thermal): open UVC thermal capture (PureThermal 3) via v4l2.
    # TODO(engine): load TensorRT engine, prepare CUDA context.
    # TODO(mavlink): pymavlink connection to UDP 14550, subscribe to GLOBAL_POSITION_INT.

    persistence = deque(maxlen=args.persistence_frames)
    logger.info("wildfire-watch infer loop starting; engine=%s", args.engine)

    while True:
        # Skeleton — replace with real capture + inference.
        rgb_score = 0.0
        thermal_delta_c = 0.0
        coords = {"lat": 0.0, "lon": 0.0, "alt_agl_m": 0.0}
        geofence_ok = True
        wind_consistent = True

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
            sig = build_signal(
                drone_id=args.drone_id,
                zone_id=args.zone_id,
                coords=coords,
                target_coords=None,  # TODO(geo): pixel_to_geo()
                signal_type=signal_type,
                confidence=confidence,
                rgb_yolo_score=rgb_score,
                thermal_delta_c=thermal_delta_c,
                frame_uris=[],  # TODO(evidence): GCS upload + URI fill
                risk_score=confidence * 100.0,
                recommended_action=recommended,
            )
            try:
                # TODO(secret): WEBHOOK_SECRET from env.
                post_signal(args.signal_endpoint, sig, secret="REPLACE_ME")
            except Exception as exc:
                logger.exception("Failed to post signal: %s", exc)
                # TODO(buffer): persist locally, retry on backoff.

            print(json.dumps(sig, indent=2))

        time.sleep(1.0 / 30.0)  # ~30 Hz capture loop placeholder


if __name__ == "__main__":
    main()
