"""Fusion-gate trip → alert routing.

When ``ml/fire_detection/infer.should_emit()`` flips True AND the
fused risk_score crosses the configured threshold, a real human (or
an integration like a fire-dept paging system) needs to know — fast.

This module is the single fan-out point. Two delivery paths:

1. **HTTP webhook** with HMAC-SHA256 signature. Same envelope shape
   as the signal POST, so an existing ingest already speaking the
   wildfire_signal protocol can be a webhook receiver.

2. **Telegram bot** — for the operator's phone. Off by default; only
   activates when both ``TELEGRAM_TOKEN`` and ``TELEGRAM_CHAT_ID``
   are set.

Both paths are best-effort: a failure in one does not block the
other. The point of the alert is to reach a human; partial delivery
beats none.

**Idempotence**. Every fire signal is routed at-most-once. We persist
the set of alerted ``signal_id``s to ``~/.wildfire/alerts.jsonl`` so a
crash-loop replay or a swarm vote that triggers twice on the same
signal can't double-page. The file is JSONL (append-only) for the
same reasons we use it elsewhere: trivial to inspect, trivial to
truncate.

The HTTP layer is lazy-imported so modules that *only* want to
introspect alert state (e.g., the dashboard) can import without
pulling ``requests`` into the dependency graph.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("wildfire_watch.alerts")


# ---------------------------------------------------------------------------
# State + config
# ---------------------------------------------------------------------------

DEFAULT_ALERT_LEDGER = Path.home() / ".wildfire" / "alerts.jsonl"

# HTTP webhook — header naming mirrors infer.py for receiver consistency.
ALERT_HMAC_HEADER = "X-Wildfire-Alert-Signature"
ALERT_TIMESTAMP_HEADER = "X-Wildfire-Alert-Timestamp"

# Default risk-score floor for "this is real, page someone." Below this we
# log_only / notify_operator via the regular signal sink. The fusion gate
# already dropped most of the noise floor — this is the second gate that
# decides whether a *human* sees it on their phone.
DEFAULT_RISK_THRESHOLD = 70.0


@dataclass
class AlertResult:
    """Outcome of a single ``maybe_alert`` call.

    - ``alerted`` is True iff at least one delivery channel returned
      success. The idempotence ledger tracks any ``alerted=True``.
    - ``channels`` lists the delivery paths that succeeded.
    - ``skipped_reason`` is set when no alert was sent (gate not
      tripped, signal already alerted, or no channels configured).
    """

    alerted: bool
    channels: list[str]
    skipped_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Idempotence ledger
# ---------------------------------------------------------------------------


def _load_alerted_ids(ledger: Path) -> set[str]:
    """Read every previously-alerted signal_id from the ledger."""
    if not ledger.exists():
        return set()
    out: set[str] = set()
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # Don't let a single corrupt line block alerting.
                continue
            sid = row.get("signal_id")
            if isinstance(sid, str):
                out.add(sid)
    except OSError:
        return out
    return out


def _record_alert(ledger: Path, signal_id: str, channels: list[str]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "signal_id": signal_id,
        "channels": channels,
        "ts": int(time.time()),
    }
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Fusion-gate detection
# ---------------------------------------------------------------------------


def fusion_gate_passed(
    signal: dict[str, Any],
    risk_threshold: float = DEFAULT_RISK_THRESHOLD,
) -> bool:
    """Did this signal trip the alert-grade fusion gate?

    Two equivalent paths. Either:
      1. The producer set ``signal['fusion_gate_passed'] = True``
         explicitly (preferred — keeps the policy near the producer), OR
      2. ``risk_score >= risk_threshold`` AND the signal is one of the
         "this is a fire-grade thing" types.

    Path (2) is a fallback so an older signal that doesn't carry the
    explicit flag still pages the operator. Once every producer ships
    the flag, path (2) becomes redundant — but harmless.
    """
    if signal.get("fusion_gate_passed") is True:
        return True

    risk = signal.get("risk_score")
    if not isinstance(risk, (int, float)) or float(risk) < risk_threshold:
        return False

    sig_type = signal.get("signal_type")
    return sig_type in {"fire", "smoke", "thermal_anomaly"}


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------


def _sign_body(body: bytes, secret: str, timestamp: str) -> str:
    """HMAC-SHA256(secret, timestamp + "." + body) → hex digest.

    Identical envelope to ``infer._sign_body`` — receivers can share
    the same verification routine.
    """
    mac = hmac.new(
        secret.encode("utf-8"),
        msg=timestamp.encode("ascii") + b"." + body,
        digestmod=hashlib.sha256,
    )
    return mac.hexdigest()


def post_webhook(
    url: str,
    signal: dict[str, Any],
    secret: str,
    *,
    timeout: float = 5.0,
) -> None:
    """POST the alert envelope. Raises on non-2xx (caller decides next steps)."""
    import requests  # noqa: PLC0415

    body = json.dumps({"alert_type": "fusion_gate_trip", "signal": signal},
                      separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    sig = _sign_body(body, secret, ts)
    r = requests.post(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            ALERT_HMAC_HEADER: sig,
            ALERT_TIMESTAMP_HEADER: ts,
        },
        timeout=timeout,
    )
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Telegram delivery
# ---------------------------------------------------------------------------


def _format_telegram(signal: dict[str, Any]) -> str:
    """Compose the operator-facing alert text. Markdown-light."""
    sid = signal.get("signal_id", "?")
    sig_type = signal.get("signal_type", "?")
    drone = signal.get("drone_id", "?")
    zone = signal.get("zone_id", "?")
    risk = signal.get("risk_score", 0)
    coords = signal.get("coords") or {}
    lat = coords.get("lat")
    lon = coords.get("lon")
    rec = signal.get("recommended_action", "?")
    coord_line = (
        f"{lat:.5f}, {lon:.5f}" if isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        else "n/a"
    )
    return (
        "wildfire-watch ALERT\n"
        f"type: {sig_type}\n"
        f"drone: {drone}\n"
        f"zone: {zone}\n"
        f"risk: {risk}\n"
        f"coords: {coord_line}\n"
        f"action: {rec}\n"
        f"signal_id: {sid}"
    )


def post_telegram(
    token: str,
    chat_id: str,
    signal: dict[str, Any],
    *,
    timeout: float = 5.0,
) -> None:
    """Send the alert to a Telegram chat via the Bot API."""
    import requests  # noqa: PLC0415

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": chat_id, "text": _format_telegram(signal)}
    r = requests.post(url, json=body, timeout=timeout)
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------


def maybe_alert(
    signal: dict[str, Any],
    *,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
    telegram_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    ledger: Path = DEFAULT_ALERT_LEDGER,
    risk_threshold: float = DEFAULT_RISK_THRESHOLD,
) -> AlertResult:
    """Route the signal to all configured alert channels iff fusion-gate trips.

    Resolution order for each parameter: explicit kwarg → environment
    variable → unset.

    Environment variables:
        ALERT_WEBHOOK_URL
        ALERT_WEBHOOK_SECRET (defaults to WILDFIRE_WEBHOOK_SECRET if absent)
        TELEGRAM_TOKEN
        TELEGRAM_CHAT_ID

    The function is intentionally tolerant: any single channel failure
    is logged and the others still ship. The signal_id is recorded in
    the ledger only if at least one channel succeeded — that way a
    transient outage on every channel leaves the ledger untouched and
    a future call can retry.
    """
    sid = signal.get("signal_id")
    if not isinstance(sid, str) or not sid:
        return AlertResult(False, [], "missing-signal-id")

    if not fusion_gate_passed(signal, risk_threshold=risk_threshold):
        return AlertResult(False, [], "gate-not-tripped")

    already = _load_alerted_ids(ledger)
    if sid in already:
        return AlertResult(False, [], "already-alerted")

    webhook_url = webhook_url or os.environ.get("ALERT_WEBHOOK_URL")
    webhook_secret = (
        webhook_secret
        or os.environ.get("ALERT_WEBHOOK_SECRET")
        or os.environ.get("WILDFIRE_WEBHOOK_SECRET")
    )
    telegram_token = telegram_token or os.environ.get("TELEGRAM_TOKEN")
    telegram_chat_id = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    channels: list[str] = []

    if webhook_url and webhook_secret:
        try:
            post_webhook(webhook_url, signal, webhook_secret)
            channels.append("webhook")
        except Exception as exc:  # noqa: BLE001
            logger.warning("alert webhook failed: %s", exc)
    elif webhook_url:
        logger.warning("ALERT_WEBHOOK_URL set without secret; skipping webhook")

    if telegram_token and telegram_chat_id:
        try:
            post_telegram(telegram_token, telegram_chat_id, signal)
            channels.append("telegram")
        except Exception as exc:  # noqa: BLE001
            logger.warning("alert telegram failed: %s", exc)

    if not channels:
        return AlertResult(False, [], "no-channel-or-all-failed")

    _record_alert(ledger, sid, channels)
    return AlertResult(True, channels, None)
