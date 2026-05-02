"""Unit tests for HMAC signing + on-disk retry buffer.

These cover the failure-mode boundary:
  - 200 OK   -> nothing buffered
  - 502 Gateway -> signal lands in retry_dir, drains on next call
  - HMAC over (timestamp + body) deterministic for fixed inputs
  - Drain stops at first failure (don't bury fresh signals under stale ones)

Run:
    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/test_webhook.py -q
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from infer import (  # noqa: E402
    HMAC_HEADER,
    HMAC_TIMESTAMP_HEADER,
    _resolve_secret,
    _sign_body,
    buffer_signal,
    build_signal,
    drain_retry_queue,
    post_signal,
    post_with_retry,
)


# ---------------------------------------------------------------------------
# Test doubles for `requests.post`.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            # Mimic requests.HTTPError without importing requests at test-collect time.
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeRequests:
    """Captures the last call so tests can assert on URL + headers + body."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[dict] = []

    def post(self, endpoint, *, data=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "endpoint": endpoint,
                "data": data,
                "json": json,
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        return _FakeResponse(self.status)


def _install_fake_requests(monkeypatch: pytest.MonkeyPatch, status: int) -> _FakeRequests:
    fake = _FakeRequests(status=status)
    fake_module = type("M", (), {"post": fake.post})
    monkeypatch.setitem(sys.modules, "requests", fake_module)
    return fake


def _example_signal() -> dict:
    return build_signal(
        drone_id="wfw-unit01",
        zone_id="test-zone",
        coords={"lat": 36.5, "lon": -121.2, "alt_agl_m": 80.0},
        target_coords=None,
        signal_type="smoke",
        confidence=0.91,
        rgb_yolo_score=0.93,
        thermal_delta_c=18.5,
        frame_uris=["gs://wildfire-watch-evidence/test/frame.jpg"],
        risk_score=78.0,
        recommended_action="notify_operator",
    )


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------


def test_sign_body_deterministic() -> None:
    body = b'{"hello":"world"}'
    a = _sign_body(body, "secret", "1700000000")
    b = _sign_body(body, "secret", "1700000000")
    assert a == b
    assert len(a) == 64  # hex SHA-256


def test_sign_body_changes_with_body_or_timestamp_or_secret() -> None:
    body = b'{"hello":"world"}'
    base = _sign_body(body, "secret", "1700000000")
    assert _sign_body(body, "secret", "1700000001") != base, "timestamp must affect MAC"
    assert _sign_body(body + b" ", "secret", "1700000000") != base, "body must affect MAC"
    assert _sign_body(body, "different", "1700000000") != base, "secret must affect MAC"


def test_sign_body_matches_independent_hmac() -> None:
    body = b'{"x":1}'
    expected = hmac.new(
        b"k", b"1700000000." + body, digestmod=hashlib.sha256
    ).hexdigest()
    assert _sign_body(body, "k", "1700000000") == expected


# ---------------------------------------------------------------------------
# post_signal — happy path + headers
# ---------------------------------------------------------------------------


def test_post_signal_200_sends_hmac_header(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_requests(monkeypatch, status=200)
    sig = _example_signal()

    post_signal("https://gs.example/ingest", sig, secret="topsecret")

    assert len(fake.calls) == 1
    call = fake.calls[0]
    headers = call["headers"]
    assert headers.get("Authorization") == "Bearer topsecret"
    assert HMAC_HEADER in headers
    assert HMAC_TIMESTAMP_HEADER in headers
    assert headers["Content-Type"] == "application/json"

    # The signature must verify against the actual body bytes.
    body = call["data"]
    ts = headers[HMAC_TIMESTAMP_HEADER]
    expected = _sign_body(body, "topsecret", ts)
    assert headers[HMAC_HEADER] == expected


def test_post_signal_502_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_requests(monkeypatch, status=502)
    with pytest.raises(RuntimeError, match="HTTP 502"):
        post_signal("https://gs.example/ingest", _example_signal(), secret="x")


# ---------------------------------------------------------------------------
# Retry buffer
# ---------------------------------------------------------------------------


def test_post_with_retry_200_no_buffer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _install_fake_requests(monkeypatch, status=200)
    sig = _example_signal()
    ok = post_with_retry(
        "https://gs.example/ingest", sig, secret="x", retry_dir=tmp_path
    )
    assert ok is True
    assert len(fake.calls) == 1
    assert list(tmp_path.glob("*.json")) == [], "no buffer on success"


def test_post_with_retry_502_lands_in_buffer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_requests(monkeypatch, status=502)
    sig = _example_signal()
    ok = post_with_retry(
        "https://gs.example/ingest", sig, secret="x", retry_dir=tmp_path
    )
    assert ok is False
    pending = list(tmp_path.glob("*.json"))
    assert len(pending) == 1
    parsed = json.loads(pending[0].read_text())
    assert parsed["signal_id"] == sig["signal_id"]


def test_buffer_signal_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    sig = _example_signal()
    path = buffer_signal(sig, retry_dir=tmp_path)
    assert path.exists()
    # No leftover .tmp from the atomic-rename path.
    assert list(tmp_path.glob("*.tmp")) == []


def test_drain_replays_then_unlinks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # First buffer one signal while the endpoint is down...
    _install_fake_requests(monkeypatch, status=502)
    sig = _example_signal()
    post_with_retry(
        "https://gs.example/ingest", sig, secret="x", retry_dir=tmp_path
    )
    assert len(list(tmp_path.glob("*.json"))) == 1

    # ...then drain successfully when the endpoint is back.
    fake_ok = _install_fake_requests(monkeypatch, status=200)
    drained, remaining = drain_retry_queue(
        "https://gs.example/ingest", "x", retry_dir=tmp_path
    )
    assert drained == 1
    assert remaining == 0
    assert list(tmp_path.glob("*.json")) == []
    # The drained body must have been the buffered signal.
    sent_body = fake_ok.calls[0]["data"]
    assert json.loads(sent_body)["signal_id"] == sig["signal_id"]


def test_drain_stops_on_first_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If delivery still fails mid-drain, we must NOT delete the failed file
    (so a fresh signal can't get buried under stale ones we silently dropped)."""
    # Buffer two signals.
    _install_fake_requests(monkeypatch, status=502)
    s1 = _example_signal()
    s2 = _example_signal()
    post_with_retry("https://gs.example", s1, secret="x", retry_dir=tmp_path)
    post_with_retry("https://gs.example", s2, secret="x", retry_dir=tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 2

    # Endpoint still 502 — drain must touch zero files.
    drained, remaining = drain_retry_queue(
        "https://gs.example", "x", retry_dir=tmp_path
    )
    assert drained == 0
    assert remaining == 2


def test_drain_drops_malformed_files(tmp_path: Path) -> None:
    bad = tmp_path / "0-corrupt.json"
    bad.write_text("not json {{{")
    drained, remaining = drain_retry_queue(
        "https://gs.example", "x", retry_dir=tmp_path
    )
    assert drained == 0
    assert remaining == 0  # corrupt file unlinked, didn't ride forever


def test_drain_missing_dir_is_noop(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    drained, remaining = drain_retry_queue(
        "https://gs.example", "x", retry_dir=missing
    )
    assert drained == 0
    assert remaining == 0


# ---------------------------------------------------------------------------
# Secret resolution
# ---------------------------------------------------------------------------


def test_resolve_secret_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WILDFIRE_WEBHOOK_SECRET", "topsecret")
    assert _resolve_secret() == "topsecret"


def test_resolve_secret_rejects_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WILDFIRE_WEBHOOK_SECRET", "REPLACE_ME")
    with pytest.raises(RuntimeError, match="placeholder"):
        _resolve_secret()


def test_resolve_secret_rejects_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WILDFIRE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="must be set"):
        _resolve_secret()
