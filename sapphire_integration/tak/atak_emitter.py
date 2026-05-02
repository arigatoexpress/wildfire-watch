"""High-level pipe: wildfire_signal -> CoT XML -> sink (server / file / stdout).

This is the convenience facade most callers want. Usage:

    from sapphire_integration.tak.atak_emitter import emit

    # to a TAK Server over TCP
    emit(signal, server="tcp://atak.local:8087")

    # to stdout (operator inspection)
    emit(signal, out="-")

    # to a file
    emit(signal, out="/tmp/cot.xml")

    # build only, no I/O
    xml = emit(signal)

When the underlying socket is unreachable, the function logs and re-raises
so the caller (CLI / hermes-bridge) can decide whether to buffer + retry.
The CLI catches OSError and prints to stderr; the Sapphire-side emitter
should buffer to disk and retry on backoff.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from .cot_event import build_cot_event

logger = logging.getLogger(__name__)


def emit(
    signal: dict[str, Any],
    *,
    server: Optional[str] = None,
    out: Optional[str] = None,
    tls_cafile: Optional[str] = None,
    tls_certfile: Optional[str] = None,
    tls_keyfile: Optional[str] = None,
    timeout_seconds: float = 5.0,
) -> str:
    """Emit a wildfire_signal as a CoT event.

    Parameters
    ----------
    signal:
        wildfire_signal v1 record (dict).
    server:
        Optional TAK URL: ``tcp://host:port``, ``tls://host:port``,
        ``udp://host:port``, ``mcast://239.2.3.1:6969``. If set, the event
        is dispatched over the wire.
    out:
        Optional file sink. ``"-"`` or ``"/dev/stdout"`` writes the XML to
        stdout. Otherwise interpreted as a filesystem path.
    tls_cafile / tls_certfile / tls_keyfile:
        TLS material when ``server`` is ``tls://...``. ``cafile`` is the
        TAK Server CA; ``certfile`` + ``keyfile`` are the operator's
        client certificate.
    timeout_seconds:
        Socket timeout (seconds).

    Returns
    -------
    str
        The CoT XML document that was emitted.
    """
    cot_xml = build_cot_event(signal)

    if out is not None:
        _write_out(cot_xml, out)

    if server is not None:
        # Lazy import — keeps `--help` working even if socket libs unhappy.
        from .tak_server_client import TAKServerClient  # noqa: PLC0415

        client = TAKServerClient(
            server,
            timeout_seconds=timeout_seconds,
            tls_cafile=tls_cafile,
            tls_certfile=tls_certfile,
            tls_keyfile=tls_keyfile,
        )
        client.send(cot_xml)
        logger.info("CoT event sent to %s", server)

    return cot_xml


def _write_out(cot_xml: str, out: str) -> None:
    """Write XML to a sink. Special-cases ``-`` and ``/dev/stdout``."""
    if out in ("-", "/dev/stdout"):
        sys.stdout.write(cot_xml)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return
    if out == "/dev/stderr":
        sys.stderr.write(cot_xml)
        sys.stderr.write("\n")
        sys.stderr.flush()
        return
    Path(out).write_text(cot_xml + "\n", encoding="utf-8")
