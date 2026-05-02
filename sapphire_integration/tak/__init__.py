"""TAK / Cursor-on-Target interop for wildfire-watch.

This package converts wildfire_signal v1 records into Cursor-on-Target (CoT)
XML events and dispatches them to a TAK Server (or stdout/file/UDP multicast).

CoT is the underlying protocol for the entire TAK ecosystem:
ATAK (Android), iTAK (iOS), WinTAK (Windows), FreeTAKServer / TAKServer.
That ecosystem is what every county fire chief, USFS Incident Management
Team, and defense-community SA platform (Anduril Lattice, Palantir Apollo,
Ondas Optimus) speaks. Emitting valid CoT is the highest-leverage interop
move for a wildfire detection pipeline.

Public surface (lazy-imported where useful):

- ``cot_event.build_cot_event(signal) -> str``         CoT XML from a v1 signal
- ``cot_types.cot_type_for_signal(signal) -> str``     signal-type → CoT code
- ``atak_emitter.emit(signal, ...) -> str``            high-level: signal -> XML -> sink
- ``tak_server_client.TAKServerClient``                TCP/UDP/TLS dispatch

Stdlib-only. ``pytak`` is the production-grade alternative; we deliberately
avoid the dependency to keep the drone payload + ground-station wheel slim.
"""

from __future__ import annotations

__all__ = [
    "build_cot_event",
    "cot_type_for_signal",
    "emit",
]

# Light re-exports. We intentionally keep these as module-level lazy imports
# so `python -m sapphire_integration.tak.cli --help` works without socket /
# ssl modules if the platform happens to lack them.

def build_cot_event(*args, **kwargs):  # noqa: D401 - thin proxy
    """Proxy to ``cot_event.build_cot_event``."""
    from .cot_event import build_cot_event as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def cot_type_for_signal(*args, **kwargs):  # noqa: D401
    """Proxy to ``cot_types.cot_type_for_signal``."""
    from .cot_types import cot_type_for_signal as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def emit(*args, **kwargs):  # noqa: D401
    """Proxy to ``atak_emitter.emit``."""
    from .atak_emitter import emit as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)
