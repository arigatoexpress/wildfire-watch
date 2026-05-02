"""Unit tests for ``ml/fire_detection/evidence.py``.

Covers the failure-mode boundary:
  - Successful upload returns canonical ``gs://`` URI, no buffer.
  - 5xx / network / auth failure routes to retry queue, URI still set.
  - Signed-URL is generated when expiry is requested AND upload succeeds.
  - ``drain_evidence_queue`` retries each buffered frame, stops on first failure.
  - Object key honours ``EVIDENCE_BUCKET`` env override.

The google-cloud-storage SDK is fully mocked — the test suite never
touches a real GCS bucket.

Run::

    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/test_evidence.py -q
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from evidence import (  # noqa: E402
    DEFAULT_BUCKET,
    UploadResult,
    build_object_key,
    drain_evidence_queue,
    gcs_uri,
    upload_frame,
)


# ---------------------------------------------------------------------------
# Fakes for the GCS SDK
# ---------------------------------------------------------------------------


class _FakeBlob:
    def __init__(
        self,
        bucket_name: str,
        key: str,
        upload_should_fail: bool = False,
        signed_url_should_fail: bool = False,
        record: list[dict[str, Any]] | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.key = key
        self._fail_upload = upload_should_fail
        self._fail_signed = signed_url_should_fail
        self._record = record if record is not None else []

    def upload_from_string(self, data: bytes, content_type: str = "image/jpeg") -> None:
        self._record.append(
            {
                "kind": "upload",
                "bucket": self.bucket_name,
                "key": self.key,
                "content_type": content_type,
                "size": len(data),
            }
        )
        if self._fail_upload:
            raise RuntimeError("simulated 502")

    def generate_signed_url(self, **kwargs: Any) -> str:
        if self._fail_signed:
            raise RuntimeError("no signing key")
        return f"https://storage.googleapis.com/{self.bucket_name}/{self.key}?sig=fake"


class _FakeBucket:
    def __init__(
        self,
        name: str,
        upload_should_fail: bool,
        signed_url_should_fail: bool,
        record: list[dict[str, Any]],
    ) -> None:
        self.name = name
        self._fail_upload = upload_should_fail
        self._fail_signed = signed_url_should_fail
        self._record = record

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(
            self.name,
            key,
            upload_should_fail=self._fail_upload,
            signed_url_should_fail=self._fail_signed,
            record=self._record,
        )


class _FakeStorageClient:
    def __init__(
        self,
        upload_should_fail: bool = False,
        signed_url_should_fail: bool = False,
    ) -> None:
        self._fail_upload = upload_should_fail
        self._fail_signed = signed_url_should_fail
        self.record: list[dict[str, Any]] = []

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(
            name,
            upload_should_fail=self._fail_upload,
            signed_url_should_fail=self._fail_signed,
            record=self.record,
        )


# ---------------------------------------------------------------------------
# Object key + URI shape
# ---------------------------------------------------------------------------


def test_build_object_key_uses_date_flight_frame_layout() -> None:
    fixed = datetime(2026, 5, 2, 18, 0, tzinfo=timezone.utc)
    key = build_object_key("flight-001", "frame_017", now=fixed)
    assert key == "2026-05-02/flight-001/frame_017.jpg"


def test_build_object_key_strips_path_traversal() -> None:
    """A malformed flight_id can't escape its date prefix."""
    fixed = datetime(2026, 5, 2, tzinfo=timezone.utc)
    key = build_object_key("../oops/flight", "../frame/01", now=fixed)
    assert ".." not in key
    assert key.startswith("2026-05-02/")


def test_gcs_uri_is_well_formed() -> None:
    assert (
        gcs_uri("wildfire-watch-evidence", "2026-05-02/f1/x.jpg")
        == "gs://wildfire-watch-evidence/2026-05-02/f1/x.jpg"
    )


def test_default_bucket_constant_matches_runbook() -> None:
    assert DEFAULT_BUCKET == "wildfire-watch-evidence"


# ---------------------------------------------------------------------------
# upload_frame — happy path
# ---------------------------------------------------------------------------


def test_upload_frame_success(tmp_path: Path) -> None:
    client = _FakeStorageClient()
    fixed = datetime(2026, 5, 2, tzinfo=timezone.utc)
    result = upload_frame(
        b"\xff\xd8jpegbytes",
        flight_id="flight-001",
        frame_id="f0001",
        bucket="wildfire-watch-evidence",
        retry_dir=tmp_path,
        storage_client_factory=lambda: client,
        now=fixed,
    )
    assert isinstance(result, UploadResult)
    assert result.uri == "gs://wildfire-watch-evidence/2026-05-02/flight-001/f0001.jpg"
    assert result.buffered is False
    assert result.signed_url is None
    assert len(client.record) == 1
    assert client.record[0]["key"] == "2026-05-02/flight-001/f0001.jpg"
    assert list(tmp_path.iterdir()) == []  # nothing buffered


def test_upload_frame_signed_url_when_requested(tmp_path: Path) -> None:
    client = _FakeStorageClient()
    fixed = datetime(2026, 5, 2, tzinfo=timezone.utc)
    result = upload_frame(
        b"data",
        flight_id="flight-001",
        frame_id="f0001",
        retry_dir=tmp_path,
        storage_client_factory=lambda: client,
        signed_url_expires_in=3600,
        now=fixed,
    )
    assert result.signed_url is not None
    assert result.signed_url.startswith("https://")
    assert "sig=fake" in result.signed_url
    assert result.buffered is False


def test_upload_frame_signed_url_failure_is_non_fatal(tmp_path: Path) -> None:
    """Workload-identity envs can't sign locally; upload still succeeds."""
    client = _FakeStorageClient(signed_url_should_fail=True)
    result = upload_frame(
        b"data",
        flight_id="flight-001",
        frame_id="f0001",
        retry_dir=tmp_path,
        storage_client_factory=lambda: client,
        signed_url_expires_in=3600,
    )
    assert result.buffered is False
    assert result.signed_url is None
    assert result.uri.startswith("gs://")


def test_upload_frame_honours_evidence_bucket_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVIDENCE_BUCKET", "alt-bucket")
    client = _FakeStorageClient()
    result = upload_frame(
        b"data",
        flight_id="flight-001",
        frame_id="f0001",
        retry_dir=tmp_path,
        storage_client_factory=lambda: client,
    )
    assert result.uri.startswith("gs://alt-bucket/")
    assert client.record[0]["bucket"] == "alt-bucket"


# ---------------------------------------------------------------------------
# upload_frame — failure routes to retry queue
# ---------------------------------------------------------------------------


def test_upload_frame_5xx_lands_in_retry_buffer(tmp_path: Path) -> None:
    client = _FakeStorageClient(upload_should_fail=True)
    fixed = datetime(2026, 5, 2, tzinfo=timezone.utc)
    result = upload_frame(
        b"\xde\xad\xbe\xef",
        flight_id="flight-001",
        frame_id="f0001",
        bucket="wildfire-watch-evidence",
        retry_dir=tmp_path,
        storage_client_factory=lambda: client,
        now=fixed,
    )
    assert result.buffered is True
    assert result.uri.endswith("2026-05-02/flight-001/f0001.jpg")
    pending = list(tmp_path.glob("*.json"))
    assert len(pending) == 1


def test_upload_frame_auth_failure_buffers(tmp_path: Path) -> None:
    """Bad creds raise on .Client() — must still buffer instead of crashing."""

    def _raises() -> Any:
        raise RuntimeError("no creds")

    result = upload_frame(
        b"data",
        flight_id="flight-001",
        frame_id="f0001",
        retry_dir=tmp_path,
        storage_client_factory=_raises,
    )
    assert result.buffered is True
    assert len(list(tmp_path.glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# drain_evidence_queue
# ---------------------------------------------------------------------------


def test_drain_evidence_queue_replays_then_unlinks(tmp_path: Path) -> None:
    bad_client = _FakeStorageClient(upload_should_fail=True)
    upload_frame(
        b"frame-a",
        flight_id="flight-001",
        frame_id="f01",
        retry_dir=tmp_path,
        storage_client_factory=lambda: bad_client,
    )
    upload_frame(
        b"frame-b",
        flight_id="flight-001",
        frame_id="f02",
        retry_dir=tmp_path,
        storage_client_factory=lambda: bad_client,
    )
    assert len(list(tmp_path.glob("*.json"))) == 2

    good_client = _FakeStorageClient()
    drained, remaining = drain_evidence_queue(
        retry_dir=tmp_path, storage_client_factory=lambda: good_client
    )
    assert drained == 2
    assert remaining == 0
    assert list(tmp_path.glob("*.json")) == []
    assert len(good_client.record) == 2


def test_drain_evidence_queue_stops_on_first_failure(tmp_path: Path) -> None:
    """A long-stale buffered frame must not bury a fresh signal."""
    bad_client = _FakeStorageClient(upload_should_fail=True)
    upload_frame(
        b"a", flight_id="f1", frame_id="f01",
        retry_dir=tmp_path, storage_client_factory=lambda: bad_client,
    )
    upload_frame(
        b"b", flight_id="f1", frame_id="f02",
        retry_dir=tmp_path, storage_client_factory=lambda: bad_client,
    )
    assert len(list(tmp_path.glob("*.json"))) == 2

    drained, remaining = drain_evidence_queue(
        retry_dir=tmp_path, storage_client_factory=lambda: bad_client
    )
    assert drained == 0
    assert remaining == 2


def test_drain_evidence_queue_drops_malformed(tmp_path: Path) -> None:
    """Corrupt JSON in the buffer must not stop progress on valid neighbours."""
    (tmp_path / "1234-bogus.json").write_text("not-json", encoding="utf-8")
    upload_frame(
        b"good",
        flight_id="f1",
        frame_id="f01",
        retry_dir=tmp_path,
        storage_client_factory=lambda: _FakeStorageClient(upload_should_fail=True),
    )
    good_client = _FakeStorageClient()
    drained, remaining = drain_evidence_queue(
        retry_dir=tmp_path, storage_client_factory=lambda: good_client
    )
    assert drained == 1
    assert remaining == 0


def test_drain_evidence_queue_empty_dir_is_noop(tmp_path: Path) -> None:
    drained, remaining = drain_evidence_queue(
        retry_dir=tmp_path / "missing",
        storage_client_factory=lambda: _FakeStorageClient(),
    )
    assert (drained, remaining) == (0, 0)
