"""wildfire-watch — Raspberry Pi telemetry collector (Phase 0).

Runs on rari1 (100.120.191.1) and rari2 (100.87.225.89). Two responsibilities:

  1. Heartbeat: append a JSONL line to a local log every HEARTBEAT_S seconds.
  2. Periodic batch: every BATCH_S seconds, package the heartbeats into a
     wildfire_signal v1 (signal_type=system_event, recommended_action=log_only)
     and POST it to the Sapphire wildfire bridge over Tailscale.

Why: it proves the Pi -> Mac mini path is alive on Tailscale, and gives us
the scaffolding for the *real* sensor collector once an air-quality / IR
sensor lands. Today it just reports CPU temp, hostname, uptime, disk free,
load avg — Pi housekeeping. None of it is fire data; it is dial-tone.

Constraints honoured:
  - stdlib only. No pip installs on the Pis. (`requests` is also tolerated
    if present — used as a fallback. `urllib.request` is the default path.)
  - Schema v1 conformance: builds the signal in-process matching exactly the
    fields enforced by ~/Code/wildfire-watch/sapphire_integration/wildfire_signal_schema.json.
    NOTE: this script intentionally does NOT import build_signal from
    ml/fire_detection/infer.py — the wildfire-watch repo is not deployed
    onto the Pi; we duplicate the minimum of fields here. The Sapphire
    bridge re-validates against the canonical JSON schema, so any drift
    is caught at ingest time.

Usage:
    python3 ground_station/pi_telemetry_collector.py \
        --pi-config ~/.wildfire-watch/pi_config.json \
        --bridge-url http://mac.local:18081/wildfire/ingest

For local dry-run (no POST):
    python3 ground_station/pi_telemetry_collector.py --dry-run \
        --pi-config /tmp/pi_config.json

Pi config file (JSON):
    {
      "pi_id": "wfw-pi01",
      "zone_id": "phase0-rari1-baseline",
      "lat": 36.4906,
      "lon": -121.1825,
      "alt_agl_m": 0.0,
      "log_dir": "/var/log/wildfire-watch"
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("wildfire_watch.pi_telemetry")

SCHEMA_VERSION = "1.0.0"
HEARTBEAT_S = 60
BATCH_S = 300  # POST a batch every 5 minutes
DEFAULT_TIMEOUT_S = 10.0


# ---------------------------------------------------------------------------
# Pi sensor reads — stock Bookworm only. No new packages required.
# ---------------------------------------------------------------------------


def read_cpu_temp_c() -> float | None:
    """Read CPU temperature in Celsius. Pi-only path; returns None elsewhere.

    /sys/class/thermal/thermal_zone0/temp is the standard Linux thermal
    zone interface (millicelsius). vcgencmd is Pi-specific and is the
    fallback if /sys is unavailable.
    """
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", encoding="utf-8") as fh:
            milli_c = int(fh.read().strip())
        return milli_c / 1000.0
    except (OSError, ValueError):
        pass
    try:
        out = subprocess.check_output(
            ["vcgencmd", "measure_temp"], timeout=2.0, text=True
        )
        m = re.search(r"temp=([\d.]+)", out)
        if m:
            return float(m.group(1))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def read_uptime_s() -> float | None:
    """Read system uptime in seconds (Linux only)."""
    try:
        with open("/proc/uptime", encoding="utf-8") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_load_avg() -> tuple[float, float, float] | None:
    """Read 1/5/15-minute load average."""
    try:
        return os.getloadavg()
    except OSError:
        return None


def read_disk_free_pct(path: str = "/") -> float | None:
    """Read percentage of disk free on `path`."""
    try:
        usage = shutil.disk_usage(path)
        return round(usage.free * 100.0 / usage.total, 2)
    except OSError:
        return None


def collect_heartbeat() -> dict:
    """Collect a single heartbeat record."""
    return {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_temp_c": read_cpu_temp_c(),
        "uptime_s": read_uptime_s(),
        "load_avg": read_load_avg(),
        "disk_free_pct": read_disk_free_pct(),
    }


# ---------------------------------------------------------------------------
# Signal construction (schema v1, intentionally duplicated — see module docstring).
# ---------------------------------------------------------------------------


def build_pi_signal(*, pi_config: dict, batch: list[dict]) -> dict:
    """Build a wildfire_signal v1 with signal_type=system_event from a batch."""
    coords = {
        "lat": float(pi_config.get("lat", 0.0)),
        "lon": float(pi_config.get("lon", 0.0)),
        "alt_agl_m": float(pi_config.get("alt_agl_m", 0.0)),
    }
    pi_id = str(pi_config.get("pi_id", socket.gethostname()))
    # drone_id pattern in schema: ^wfw-[a-z0-9]{4,16}$. Keep pi_id conformant.
    if not re.match(r"^wfw-[a-z0-9]{4,16}$", pi_id):
        pi_id = "wfw-pi01"
    zone_id = str(pi_config.get("zone_id", "phase0-pi-baseline"))
    return {
        "schema_version": SCHEMA_VERSION,
        "signal_id": str(uuid.uuid4()),
        "drone_id": pi_id,
        "zone_id": zone_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "coords": coords,
        "target_coords": None,
        "signal_type": "system_event",
        "signal_subtype": "phase_0/pi_telemetry_heartbeat",
        "confidence": 1.0,
        "evidence": {
            # Schema requires at least one frame_uri (minItems: 1). We use a
            # synthetic file:// URI pointing to the local heartbeat log.
            "frame_uris": [
                f"file://{Path(pi_config.get('log_dir', '/tmp/wildfire-watch')).as_posix()}/"
                f"{pi_id}_heartbeat.jsonl"
            ],
            "model_outputs": {
                "rgb_yolo_score": 0.0,
                "thermal_delta_c": 0.0,
            },
        },
        "risk_score": 0.0,
        "recommended_action": "log_only",
        "geofence_status": {
            "in_authorized_zone": True,
            "tfr_active": False,
            "remote_id_active": False,
        },
        # Custom batch payload is not in the canonical schema. The bridge
        # validator with additionalProperties:false will reject this — so we
        # stuff the batch JSON into a model_outputs note instead.
    }


def attach_batch_note(signal: dict, batch: list[dict]) -> dict:
    """Squeeze the batch into model_outputs.anomaly_score + frame_uris note.

    The schema's `evidence.model_outputs` allows free-form numeric fields,
    so we record batch_size there and use a single data: URI to carry the
    batch payload. additionalProperties:false on the top level prevents us
    from adding a `batch` field.
    """
    signal["evidence"]["model_outputs"]["anomaly_score"] = float(len(batch))
    # data:application/json URI so any reader can decode it; capped to 8 KB
    # so we don't blow up the JSONL receiver.
    encoded = json.dumps({"heartbeats": batch}, separators=(",", ":"))
    if len(encoded) > 8000:
        encoded = json.dumps({"heartbeats": batch[-10:], "truncated": True}, separators=(",", ":"))
    signal["evidence"]["frame_uris"].append(
        f"data:application/json;base64,{_b64(encoded)}"
    )
    return signal


def _b64(text: str) -> str:
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# POST helpers — urllib first, requests fallback if installed.
# ---------------------------------------------------------------------------


def post_signal(url: str, signal: dict, timeout: float = DEFAULT_TIMEOUT_S) -> tuple[int, str]:
    """POST signal as JSON. Returns (status_code, body_snippet)."""
    body = json.dumps(signal).encode("utf-8")
    try:
        import requests  # type: ignore  # noqa: PLC0415
        r = requests.post(url, data=body, headers={"Content-Type": "application/json"},
                          timeout=timeout)
        return (r.status_code, r.text[:200])
    except ImportError:
        pass
    # Fallback: urllib.
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (resp.status, resp.read(200).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return (exc.code, str(exc))
    except urllib.error.URLError as exc:
        return (0, f"urlerror: {exc}")


# ---------------------------------------------------------------------------
# Local log
# ---------------------------------------------------------------------------


def append_jsonl(log_dir: Path, name: str, record: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / name
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Config + main loop
# ---------------------------------------------------------------------------


def load_pi_config(path: Path) -> dict:
    if not path.exists():
        # Be tolerant: provide sensible defaults so the script can run
        # before the operator drops a real config.
        logger.warning("pi config not found at %s — using defaults", path)
        return {
            "pi_id": "wfw-pi01",
            "zone_id": "phase0-pi-baseline",
            "lat": 0.0,
            "lon": 0.0,
            "alt_agl_m": 0.0,
            "log_dir": str(Path.home() / ".wildfire-watch" / "logs"),
        }
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch Pi telemetry collector.")
    p.add_argument("--pi-config", default=str(Path.home() / ".wildfire-watch" / "pi_config.json"))
    p.add_argument("--bridge-url", default="http://mac.local:18081/wildfire/ingest",
                   help="POST target. mac.local resolves over mDNS/Tailscale.")
    p.add_argument("--heartbeat-s", type=int, default=HEARTBEAT_S)
    p.add_argument("--batch-s", type=int, default=BATCH_S)
    p.add_argument("--once", action="store_true",
                   help="Collect ONE heartbeat + POST one batch, then exit. Useful for cron / smoke tests.")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip the HTTP POST. Local JSONL logging still happens.")
    return p.parse_args()


def run_once(args: argparse.Namespace, pi_config: dict) -> int:
    """Single heartbeat -> single batch POST. Smoke-test mode."""
    log_dir = Path(pi_config.get("log_dir", "/tmp/wildfire-watch")).expanduser()
    pi_id = pi_config.get("pi_id", "wfw-pi01")

    hb = collect_heartbeat()
    append_jsonl(log_dir, f"{pi_id}_heartbeat.jsonl", hb)

    signal = build_pi_signal(pi_config=pi_config, batch=[hb])
    attach_batch_note(signal, [hb])

    if args.dry_run:
        sys.stdout.write(json.dumps(signal) + "\n")
        return 0

    status, body = post_signal(args.bridge_url, signal)
    if status != 200:
        logger.error("POST %s failed: status=%s body=%s", args.bridge_url, status, body)
        return 1
    logger.info("POST %s ok: status=%s", args.bridge_url, status)
    return 0


def run_forever(args: argparse.Namespace, pi_config: dict) -> int:
    log_dir = Path(pi_config.get("log_dir", "/tmp/wildfire-watch")).expanduser()
    pi_id = pi_config.get("pi_id", "wfw-pi01")
    batch: list[dict] = []
    last_post = time.monotonic()

    logger.info(
        "starting collector pi_id=%s heartbeat=%ds batch=%ds bridge=%s log_dir=%s",
        pi_id, args.heartbeat_s, args.batch_s, args.bridge_url, log_dir,
    )

    while True:
        try:
            hb = collect_heartbeat()
            append_jsonl(log_dir, f"{pi_id}_heartbeat.jsonl", hb)
            batch.append(hb)

            now = time.monotonic()
            if (now - last_post) >= args.batch_s and batch:
                signal = build_pi_signal(pi_config=pi_config, batch=batch)
                attach_batch_note(signal, batch)
                if args.dry_run:
                    logger.info("dry-run batch (%d heartbeats) signal_id=%s",
                                len(batch), signal["signal_id"])
                else:
                    status, body = post_signal(args.bridge_url, signal)
                    if status == 200:
                        logger.info("posted batch of %d heartbeats", len(batch))
                    else:
                        logger.warning("POST failed status=%s body=%s — keeping batch",
                                       status, body)
                        # Keep batch so it gets retried on the next tick.
                        time.sleep(args.heartbeat_s)
                        continue
                batch = []
                last_post = now
        except Exception as exc:  # noqa: BLE001 — never crash the loop
            logger.exception("heartbeat tick failed: %s", exc)
        time.sleep(args.heartbeat_s)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    pi_config = load_pi_config(Path(args.pi_config).expanduser())
    if args.once:
        return run_once(args, pi_config)
    return run_forever(args, pi_config)


if __name__ == "__main__":
    sys.exit(main())
