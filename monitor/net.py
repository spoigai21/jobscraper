"""Network helpers for the monitor process."""

from __future__ import annotations

import socket

import urllib3.util.connection as urllib3_connection


def force_ipv4() -> None:
    """Make urllib3/requests connect over IPv4 only.

    Railway containers have no IPv6 route, so hosts that publish an AAAA record
    (e.g. ntfy.sh) fail with ``[Errno 101] Network is unreachable`` when the
    resolver hands back the IPv6 address first. Restricting the address family
    to AF_INET avoids that path while leaving IPv4-only hosts unaffected.
    """

    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
