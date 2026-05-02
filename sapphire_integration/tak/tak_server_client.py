"""Wire transport for CoT events.

TAK Servers (TAK Server, FreeTAKServer) accept CoT events over three
canonical transports:

  * **TCP** (preferred) — the default streaming port is 8087 (cleartext)
    or 8089 (TLS-mutual-auth). Persistent connection; emit events as
    framed XML.
  * **TLS over TCP** — the production default for TAK Server. Mutual TLS
    with client cert pinned to a TAK Server certificate authority.
  * **UDP unicast** to a TAK Server (port 8088 historically, configurable).
  * **UDP multicast** to ``239.2.3.1:6969`` for self-position broadcast on
    a local subnet (the SA mesh convention used by ATAK in the field).

This module provides a small synchronous client. We deliberately keep this
simple and stdlib-only:

  - ``socket`` for TCP / UDP.
  - ``ssl`` for TLS (lazy-imported; no top-level dep on the ssl module so
    bare CLI ``--help`` works on stripped-down builds).

Federation (TAK Server-to-Server federated identity / KMS / data filters)
is **out of scope** here — it is an enterprise feature; production
deployments should run a TAK Server and federate via its admin console.

Cert-pinning pattern (documented; not yet implemented):

    import ssl
    ctx = ssl.create_default_context(cafile="/etc/wfw/takserver-ca.pem")
    ctx.load_cert_chain(certfile="client.pem", keyfile="client.key")
    # Pin against a known SHA-256 of the server cert at handshake-time
    # via a callback if you need belt-and-suspenders.

"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_TAK_TCP_PORT = 8087
DEFAULT_TAK_TLS_PORT = 8089
DEFAULT_TAK_UDP_PORT = 8088
SA_MULTICAST_GROUP = "239.2.3.1"
SA_MULTICAST_PORT = 6969


@dataclass(frozen=True)
class TAKEndpoint:
    """Parsed TAK destination."""
    scheme: str  # tcp | tls | udp | mcast
    host: str
    port: int

    @classmethod
    def parse(cls, url: str) -> "TAKEndpoint":
        """Parse a tak:// (or tcp:// / tls:// / udp://) URL.

        Examples:
            tcp://atak.local:8087
            tls://takserver.example:8089
            udp://10.0.0.5:8088
            mcast://239.2.3.1:6969
            tak://atak.local       (defaults to tcp:8087)
        """
        if "://" not in url:
            url = f"tcp://{url}"
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme == "tak":
            scheme = "tcp"
        if scheme not in {"tcp", "tls", "udp", "mcast"}:
            raise ValueError(f"unsupported TAK scheme {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError(f"missing host in TAK URL {url!r}")

        default_port = {
            "tcp": DEFAULT_TAK_TCP_PORT,
            "tls": DEFAULT_TAK_TLS_PORT,
            "udp": DEFAULT_TAK_UDP_PORT,
            "mcast": SA_MULTICAST_PORT,
        }[scheme]
        port = parsed.port or default_port
        return cls(scheme=scheme, host=parsed.hostname, port=port)


class TAKServerClient:
    """One-shot synchronous CoT dispatch.

    Not a long-lived persistent connection — for that use ``pytak`` or roll
    a tornado/asyncio loop. This client is for fire-and-forget emission
    from a CLI / batch script.
    """

    def __init__(
        self,
        endpoint: TAKEndpoint | str,
        *,
        timeout_seconds: float = 5.0,
        tls_cafile: Optional[str] = None,
        tls_certfile: Optional[str] = None,
        tls_keyfile: Optional[str] = None,
    ) -> None:
        self.endpoint = (
            endpoint if isinstance(endpoint, TAKEndpoint) else TAKEndpoint.parse(endpoint)
        )
        self.timeout_seconds = timeout_seconds
        self.tls_cafile = tls_cafile
        self.tls_certfile = tls_certfile
        self.tls_keyfile = tls_keyfile

    def send(self, cot_xml: str) -> None:
        """Send a CoT XML payload to the configured endpoint."""
        if not isinstance(cot_xml, str):
            raise TypeError("cot_xml must be a str (XML document)")
        payload = cot_xml.encode("utf-8") if not cot_xml.endswith("\n") else cot_xml.encode("utf-8")

        scheme = self.endpoint.scheme
        if scheme == "tcp":
            self._send_tcp(payload)
        elif scheme == "tls":
            self._send_tls(payload)
        elif scheme == "udp":
            self._send_udp_unicast(payload)
        elif scheme == "mcast":
            self._send_udp_multicast(payload)
        else:  # pragma: no cover - validated in TAKEndpoint.parse
            raise ValueError(f"unsupported scheme {scheme!r}")

    # --- transports ---

    def _send_tcp(self, payload: bytes) -> None:
        with socket.create_connection(
            (self.endpoint.host, self.endpoint.port),
            timeout=self.timeout_seconds,
        ) as sock:
            sock.sendall(payload)

    def _send_tls(self, payload: bytes) -> None:
        # Lazy import: ssl is in stdlib but importing it on a stripped-down
        # micropython / embedded interpreter could fail.
        import ssl  # noqa: PLC0415

        ctx = ssl.create_default_context(cafile=self.tls_cafile)
        if self.tls_certfile and self.tls_keyfile:
            ctx.load_cert_chain(certfile=self.tls_certfile, keyfile=self.tls_keyfile)
        with socket.create_connection(
            (self.endpoint.host, self.endpoint.port),
            timeout=self.timeout_seconds,
        ) as raw:
            with ctx.wrap_socket(raw, server_hostname=self.endpoint.host) as sock:
                sock.sendall(payload)

    def _send_udp_unicast(self, payload: bytes) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout_seconds)
            sock.sendto(payload, (self.endpoint.host, self.endpoint.port))

    def _send_udp_multicast(self, payload: bytes) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(self.timeout_seconds)
            sock.sendto(payload, (self.endpoint.host, self.endpoint.port))


def send_self_position_multicast(
    cot_xml: str,
    *,
    group: str = SA_MULTICAST_GROUP,
    port: int = SA_MULTICAST_PORT,
    ttl: int = 2,
    timeout_seconds: float = 1.0,
) -> None:
    """One-shot UDP multicast of a self-position CoT event."""
    payload = cot_xml.encode("utf-8") if not cot_xml.endswith("\n") else cot_xml.encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        sock.settimeout(timeout_seconds)
        sock.sendto(payload, (group, port))
