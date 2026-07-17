"""One-time startup network probe to diagnose egress reachability.

Logs exactly what the running container can and cannot reach so we can tell
whether a delivery failure is ntfy-specific, a broader routing problem, or an
IPv4/IPv6 issue. Safe to run at startup; every check is time-boxed and never
raises.
"""

from __future__ import annotations

import logging
import socket
import time

import requests

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 8.0

NTFY_IPV4 = "159.203.148.75"


def ntfy_reachable(timeout: float = _CONNECT_TIMEOUT) -> bool:
    """Silent TCP connectivity check to ntfy.sh (no HTTP, no push sent).

    Used by the reachability watcher to detect when Railway's egress can reach
    ntfy.sh again (i.e. the IP block has lifted). A bare SYN every few minutes
    is negligible traffic and won't re-trigger abuse protection.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((NTFY_IPV4, 443))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        sock.close()

# (label, host, port). Controls are widely-reachable anycast endpoints; if these
# fail too, the problem is general Railway egress rather than the destination.
_TCP_TARGETS: tuple[tuple[str, str, int], ...] = (
    ("ntfy.sh (IPv4 A record)", "159.203.148.75", 443),
    ("ntfy.sh :80", "159.203.148.75", 80),
    ("Cloudflare 1.1.1.1", "1.1.1.1", 443),
    ("Google DNS 8.8.8.8", "8.8.8.8", 443),
    ("github.com", "github.com", 443),
    # DigitalOcean control: a different DO host/range. If this reaches DO but
    # ntfy.sh does not, ntfy.sh is blocking our egress IP (not a DO route issue).
    ("caddyserver.com (DigitalOcean)", "caddyserver.com", 443),
    ("DO 165.227 range host", "165.227.20.207", 443),
)


def _log_dns(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[probe] getaddrinfo(%s) failed: %r", host, exc)
        return
    seen = []
    for family, _type, _proto, _canon, sockaddr in infos:
        fam = "IPv6" if family == socket.AF_INET6 else "IPv4"
        seen.append(f"{fam} {sockaddr[0]}")
    logger.info("[probe] DNS %s -> %s", host, ", ".join(seen) or "(none)")


def _tcp_connect(label: str, host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[probe] %s: DNS failed: %r", label, exc)
        return
    # Try every resolved address so we can see IPv6-vs-IPv4 behavior per host.
    seen_addrs: set[tuple[int, str]] = set()
    for family, _type, _proto, _canon, sockaddr in infos:
        key = (family, sockaddr[0])
        if key in seen_addrs:
            continue
        seen_addrs.add(key)
        fam = "IPv6" if family == socket.AF_INET6 else "IPv4"
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)
        start = time.monotonic()
        try:
            sock.connect(sockaddr)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                "[probe] %s: CONNECT OK (%s %s) in %.0fms",
                label, fam, sockaddr[0], elapsed,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(
                "[probe] %s: CONNECT FAIL (%s %s) after %.0fms: %r",
                label, fam, sockaddr[0], elapsed, exc,
            )
        finally:
            sock.close()


def _log_egress_ip() -> None:
    for label, url in (
        ("IPv4 egress", "https://api.ipify.org"),
        ("egress (any)", "https://ifconfig.me/ip"),
    ):
        try:
            resp = requests.get(url, timeout=_CONNECT_TIMEOUT)
            if resp.ok:
                logger.info("[probe] %s (%s): %s", label, url, resp.text.strip())
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("[probe] %s (%s) failed: %r", label, url, exc)


def run_network_probe() -> None:
    """Run the probe once; log results. Never raises."""
    logger.info("[probe] ===== startup network probe begin =====")
    try:
        _log_dns("ntfy.sh")
        _log_dns("github.com")
        _log_egress_ip()
        for label, host, port in _TCP_TARGETS:
            _tcp_connect(label, host, port)
    except Exception:
        logger.exception("[probe] unexpected error in network probe")
    logger.info("[probe] ===== startup network probe end =====")
