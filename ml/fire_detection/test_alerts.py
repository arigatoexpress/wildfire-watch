"""Unit tests for the fusion-gate alert router.

Covers:
  - fusion_gate_passed: explicit flag wins; risk floor + signal_type fallback.
  - maybe_alert: webhook + telegram fan-out, partial failure tolerance.
  - Idempotence: ledger blocks a duplicate alert for the same signal_id.
  - HMAC envelope shape on the webhook POST.

Run::

    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/test_alerts.py -q
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from alerts import (  # noqa: E402
    ALERT_HMAC_HEADER,
    ALERT_TIMESTAMP_HEADER,
    DEFAULT_RISK_THRESHOLD,
    AlertResult,
    fusion_gate_passed,
    maybe_alert,
)


# ---------------------------------------------------------------------------
# Test doubles for `requests`
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeRequests:
    """Records every POST so tests can assert on URL / headers / body."""

    def __init__(self, *, telegram_status: int = 200, webhook_status: int = 200) -> None:
        self.telegram_status = telegram_status
        self.webhook_status = webhook_status
        self.calls: list[dict[str, Any]] = []

    def post(self, url, *, data=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "data": data,
                "json": json,
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        if "telegram.org" in url:
            return _FakeResponse(self.telegram_status)
        return _FakeResponse(self.webhook_status)


def _install_fake_requests(monkeypatch: pytest.MonkeyPatch, fake: _FakeRequests) -> None:
    fake_module = type("M", (), {"post": fake.post})
    monkeypatch.setitem(sys.modules, "requests", fake_module)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _signal(
    *,
    signal_id: str | None = None,
    risk: float = 85.0,
    sig_type: str = "fire",
    fusion_flag: bool | None = None,
) -> dict[str, Any]:
    sig = {
        "schema_version": "1.0.0",
        "signal_id": signal_id or str(uuid.uuid4()),
        "drone_id": "wfw-unit01",
        "zone_id": "slate-river-drainage",
        "timestamp": "2026-05-02T18:00:00Z",
        "coords": {"lat": 38.91, "lon": -107.0, "alt_agl_m": 80.0},
        "signal_type": sig_type,
        "confidence": 0.92,
        "evidence": {"frame_uris": ["gs://b/frame.jpg"]},
        "risk_score": risk,
        "recommended_action": "notify_fire_dept",
    }
    if fusion_flag is not None:
        sig["fusion_gate_passed"] = fusion_flag
    return sig


# ---------------------------------------------------------------------------
# fusion_gate_passed
# ---------------------------------------------------------------------------


def test_fusion_gate_explicit_flag_wins() -> None:
    sig = _signal(risk=10.0, sig_type="anomaly", fusion_flag=True)
    assert fusion_gate_passed(sig) is True


def test_fusion_gate_risk_floor_passes() -> None:
    sig = _signal(risk=DEFAULT_RISK_THRESHOLD, sig_type="fire")
    assert fusion_gate_passed(sig) is True


def test_fusion_gate_below_floor_fails() -> None:
    sig = _signal(risk=DEFAULT_RISK_THRESHOLD - 0.1, sig_type="fire")
    assert fusion_gate_passed(sig) is False


def test_fusion_gate_blocks_low_severity_signal_types() -> None:
    """system_event / wildlife / anomaly never trip the alert gate."""
    for st in ["system_event", "wildlife", "anomaly"]:
        sig = _signal(risk=99.0, sig_type=st)
        assert fusion_gate_passed(sig) is False, st


def test_fusion_gate_handles_missing_risk() -> None:
    sig = _signal(risk=99.0, sig_type="fire")
    sig.pop("risk_score")
    assert fusion_gate_passed(sig) is False


# ---------------------------------------------------------------------------
# maybe_alert — channels
# ---------------------------------------------------------------------------


def test_maybe_alert_webhook_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    sig = _signal()
    res = maybe_alert(
        sig,
        webhook_url="https://example.com/hook",
        webhook_secret="s3cr3t",
        ledger=tmp_path / "alerts.jsonl",
    )
    assert isinstance(res, AlertResult)
    assert res.alerted is True
    assert res.channels == ["webhook"]
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://example.com/hook"
    assert ALERT_HMAC_HEADER in call["headers"]
    assert ALERT_TIMESTAMP_HEADER in call["headers"]
    assert call["headers"]["Content-Type"] == "application/json"
    body = json.loads(call["data"])
    assert body["alert_type"] == "fusion_gate_trip"
    assert body["signal"]["signal_id"] == sig["signal_id"]


def test_maybe_alert_telegram_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    res = maybe_alert(
        _signal(),
        telegram_token="bot:tok",
        telegram_chat_id="42",
        ledger=tmp_path / "alerts.jsonl",
    )
    assert res.channels == ["telegram"]
    assert "api.telegram.org" in fake.calls[0]["url"]
    assert fake.calls[0]["json"]["chat_id"] == "42"
    assert "ALERT" in fake.calls[0]["json"]["text"]


def test_maybe_alert_both_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    res = maybe_alert(
        _signal(),
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        telegram_token="bot:tok",
        telegram_chat_id="42",
        ledger=tmp_path / "alerts.jsonl",
    )
    assert set(res.channels) == {"webhook", "telegram"}
    assert len(fake.calls) == 2


def test_maybe_alert_no_channels_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    res = maybe_alert(_signal(), ledger=tmp_path / "alerts.jsonl")
    assert res.alerted is False
    assert res.skipped_reason == "no-channel-or-all-failed"
    assert fake.calls == []


def test_maybe_alert_resolves_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://env.example/hook")
    monkeypatch.setenv("ALERT_WEBHOOK_SECRET", "envsecret")
    monkeypatch.setenv("TELEGRAM_TOKEN", "bot:env")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "100")
    res = maybe_alert(_signal(), ledger=tmp_path / "alerts.jsonl")
    assert set(res.channels) == {"webhook", "telegram"}
    urls = {c["url"] for c in fake.calls}
    assert "https://env.example/hook" in urls


# ---------------------------------------------------------------------------
# maybe_alert — gate + idempotence
# ---------------------------------------------------------------------------


def test_maybe_alert_no_alert_when_gate_not_tripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    sig = _signal(risk=10.0, sig_type="anomaly")
    res = maybe_alert(
        sig,
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        ledger=tmp_path / "alerts.jsonl",
    )
    assert res.alerted is False
    assert res.skipped_reason == "gate-not-tripped"
    assert fake.calls == []


def test_maybe_alert_idempotent_per_signal_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    ledger = tmp_path / "alerts.jsonl"
    sid = str(uuid.uuid4())

    first = maybe_alert(
        _signal(signal_id=sid),
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        ledger=ledger,
    )
    assert first.alerted is True
    assert len(fake.calls) == 1

    second = maybe_alert(
        _signal(signal_id=sid),
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        ledger=ledger,
    )
    assert second.alerted is False
    assert second.skipped_reason == "already-alerted"
    assert len(fake.calls) == 1  # no second POST


def test_maybe_alert_partial_failure_records_succeeding_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Webhook 502 + telegram 200 still records the signal as alerted (telegram only)."""
    fake = _FakeRequests(webhook_status=502, telegram_status=200)
    _install_fake_requests(monkeypatch, fake)
    res = maybe_alert(
        _signal(),
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        telegram_token="bot:tok",
        telegram_chat_id="42",
        ledger=tmp_path / "alerts.jsonl",
    )
    assert res.alerted is True
    assert res.channels == ["telegram"]


def test_maybe_alert_all_channels_fail_does_not_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If every channel raises, the ledger stays empty so a retry can fire later."""
    fake = _FakeRequests(webhook_status=503, telegram_status=503)
    _install_fake_requests(monkeypatch, fake)
    ledger = tmp_path / "alerts.jsonl"
    res = maybe_alert(
        _signal(),
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        telegram_token="bot:tok",
        telegram_chat_id="42",
        ledger=ledger,
    )
    assert res.alerted is False
    assert res.skipped_reason == "no-channel-or-all-failed"
    assert not ledger.exists()


def test_maybe_alert_signal_without_id_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    sig = _signal()
    sig.pop("signal_id")
    res = maybe_alert(
        sig,
        webhook_url="https://example.com/hook",
        webhook_secret="s",
        ledger=tmp_path / "alerts.jsonl",
    )
    assert res.alerted is False
    assert res.skipped_reason == "missing-signal-id"
