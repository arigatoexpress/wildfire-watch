"""GCS evidence upload + signed-URL helper.

Closes the `TODO(evidence)` in ``infer.main()``. Detection frames captured
on the drone (Phase 1) or from the post-flight Mavic SD card (Phase 0)
are uploaded to a GCS bucket so consumers — the Sapphire dashboard, the
fire-department reviewer UI, the audit trail — can pull them by URI.

Design choices:

- **Bucket name is configurable** via ``EVIDENCE_BUCKET`` (default
  ``wildfire-watch-evidence``) so an operator can split per-county
  buckets without redeploying.
- **Auth is Application Default Credentials.** On Cloud Run the runtime
  service account is picked up automatically; on the Mac mini, ``gcloud
  auth application-default login`` once is enough.
- **Object key is deterministic**: ``<date>/<flight-id>/<frame-id>.jpg``.
  Re-uploads are idempotent (same key → overwritten content), and a
  date-prefix makes lifecycle rules trivial later.
- **Failures are non-fatal**. If GCS is down or auth is wrong, the frame
  bytes are appended to the same on-disk retry queue used by the
  webhook (``~/.wildfire/retry-evidence``). ``drain_evidence_queue``
  retries on next boot.
- **Signed URLs are off by default.** Some consumers (Sapphire bridge)
  need authenticated URIs; others (a public reviewer UI) need
  short-lived signed URLs. The caller decides via
  ``signed_url_expires_in``.

The ``google-cloud-storage`` SDK is **lazy-imported** inside
``upload_frame`` so that the rest of the code (tests, simulator,
valuation CLI) keeps working in a stock venv. The single test suite
mocks the SDK directly to keep CI from needing GCP creds.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("wildfire_watch.evidence")


DEFAULT_BUCKET = "wildfire-watch-evidence"
DEFAULT_EVIDENCE_RETRY_DIR = Path.home() / ".wildfire" / "retry-evidence"


def _bucket_name() -> str:
    """Resolve bucket name from env, falling back to the canonical default."""
    return os.environ.get("EVIDENCE_BUCKET", DEFAULT_BUCKET)


def _date_prefix(now: Optional[datetime] = None) -> str:
    """``YYYY-MM-DD`` UTC partition prefix.

    Date-bucketing is the lifecycle-rule sweet spot: GCS Object Lifecycle
    Management can age out anything older than N days with a single rule.
    """
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%d")


def build_object_key(
    flight_id: str,
    frame_id: str,
    *,
    now: Optional[datetime] = None,
    extension: str = "jpg",
) -> str:
    """Construct a stable GCS object key.

    Layout: ``<date>/<flight-id>/<frame-id>.<ext>``. Slashes inside
    components are replaced with ``_`` so a malformed flight_id can't
    silently create a nested directory.
    """
    safe_flight = flight_id.replace("/", "_").replace("..", "_")
    safe_frame = frame_id.replace("/", "_").replace("..", "_")
    return f"{_date_prefix(now)}/{safe_flight}/{safe_frame}.{extension}"


def gcs_uri(bucket: str, key: str) -> str:
    """``gs://<bucket>/<key>`` — what the Sapphire bridge stores."""
    return f"gs://{bucket}/{key}"


@dataclass
class UploadResult:
    """Return shape from ``upload_frame``.

    - ``uri`` is always populated (even on retry-buffer fallback) so the
      signal can carry a stable identifier.
    - ``signed_url`` is set only when ``signed_url_expires_in`` was passed
      AND the upload reached GCS.
    - ``buffered`` is True when the frame landed in the retry queue
      instead of GCS.
    """

    uri: str
    signed_url: Optional[str] = None
    buffered: bool = False


# ---------------------------------------------------------------------------
# GCS client wiring (lazy)
# ---------------------------------------------------------------------------


def _get_storage_client():  # pragma: no cover - thin import wrapper
    """Lazy-import google-cloud-storage. Mocked in tests."""
    from google.cloud import storage  # noqa: PLC0415

    return storage.Client()


# ---------------------------------------------------------------------------
# Upload + retry queue
# ---------------------------------------------------------------------------


def _retry_path(retry_dir: Path) -> Path:
    """One file per buffered frame: ``<unix_ts>-<uuid>.json``."""
    return retry_dir / f"{int(time.time())}-{uuid.uuid4()}.json"


def _buffer_frame(
    frame_bytes: bytes,
    bucket: str,
    key: str,
    retry_dir: Path,
) -> Path:
    """Persist (bytes, target) so a future drain can retry."""
    retry_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "bucket": bucket,
        "key": key,
        # Hex is bigger than base64 but trivial to round-trip with stdlib only.
        "frame_hex": frame_bytes.hex(),
        "buffered_at": int(time.time()),
    }
    path = _retry_path(retry_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    return path


def upload_frame(
    frame_bytes: bytes,
    flight_id: str,
    frame_id: str,
    *,
    bucket: Optional[str] = None,
    content_type: str = "image/jpeg",
    signed_url_expires_in: Optional[int] = None,
    retry_dir: Path = DEFAULT_EVIDENCE_RETRY_DIR,
    storage_client_factory=_get_storage_client,
    now: Optional[datetime] = None,
) -> UploadResult:
    """Upload a single detection frame to GCS.

    On a 5xx / network failure / auth failure, the frame bytes are
    appended to ``retry_dir`` and a ``buffered=True`` ``UploadResult``
    is returned with the canonical ``gs://`` URI so the signal still
    carries a stable identifier.

    ``signed_url_expires_in`` is the number of seconds the optional
    signed URL is valid for. Pass ``3600`` for a 1-hour link.
    """
    bucket_name = bucket or _bucket_name()
    key = build_object_key(flight_id, frame_id, now=now)
    uri = gcs_uri(bucket_name, key)

    try:
        client = storage_client_factory()
        gcs_bucket = client.bucket(bucket_name)
        blob = gcs_bucket.blob(key)
        blob.upload_from_string(frame_bytes, content_type=content_type)

        signed: Optional[str] = None
        if signed_url_expires_in is not None and signed_url_expires_in > 0:
            try:
                signed = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(seconds=signed_url_expires_in),
                    method="GET",
                )
            except Exception as exc:  # noqa: BLE001 - signed-url is best-effort
                # Common cause: workload identity has no private key, so the
                # SDK can't sign locally. The upload still succeeded — keep
                # the canonical URI and let the consumer pull via auth.
                logger.info(
                    "signed-url unavailable for %s (%s); upload still ok", key, exc
                )

        return UploadResult(uri=uri, signed_url=signed, buffered=False)

    except Exception as exc:  # noqa: BLE001 - every upload failure routes to retry
        path = _buffer_frame(frame_bytes, bucket_name, key, retry_dir)
        logger.warning(
            "evidence upload failed for %s (%s); buffered to %s", key, exc, path
        )
        return UploadResult(uri=uri, signed_url=None, buffered=True)


def drain_evidence_queue(
    retry_dir: Path = DEFAULT_EVIDENCE_RETRY_DIR,
    *,
    storage_client_factory=_get_storage_client,
    max_per_call: int = 64,
) -> tuple[int, int]:
    """Replay buffered frames to GCS.

    Mirrors ``infer.drain_retry_queue``: stops on first failure so a
    long-stale buffer can't bury a fresh upload.
    """
    if not retry_dir.exists():
        return (0, 0)

    pending = sorted(retry_dir.glob("*.json"))
    drained = 0
    client: Any = None
    for path in pending[:max_per_call]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("retry-evidence: dropping malformed %s: %s", path.name, exc)
            path.unlink(missing_ok=True)
            continue

        try:
            frame_bytes = bytes.fromhex(payload["frame_hex"])
            bucket = payload["bucket"]
            key = payload["key"]
        except (KeyError, ValueError) as exc:
            logger.warning("retry-evidence: dropping malformed %s: %s", path.name, exc)
            path.unlink(missing_ok=True)
            continue

        try:
            if client is None:
                client = storage_client_factory()
            blob = client.bucket(bucket).blob(key)
            blob.upload_from_string(frame_bytes, content_type="image/jpeg")
        except Exception as exc:  # noqa: BLE001 - tolerate everything, retry next boot
            logger.info("retry-evidence: still failing on %s: %s", path.name, exc)
            break

        path.unlink(missing_ok=True)
        drained += 1

    remaining = len(list(retry_dir.glob("*.json")))
    return (drained, remaining)
