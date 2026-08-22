"""SSRF guard for the generic ingestion connector.

The generic connector fetches a user-supplied `config.url` server-side, so every URL (and every
redirect hop) MUST be validated before a request is made: only http/https, and the resolved IPs
must be public (never loopback / private / link-local / cloud-metadata / reserved). This is the
mandatory control for R2 Leg 5b (see the OWASP gate). It is best-effort against DNS rebinding
(validation happens just before the fetch); combined with disabling automatic redirects and
re-validating each hop, it blocks the practical SSRF vectors for an outbound HTML/JSON scraper.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")


class SsrfError(Exception):
    """Raised when a URL targets a non-public / disallowed destination."""


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    # IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) must be judged on the embedded v4 address.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _ip_is_blocked(mapped)
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    )


def _resolve(host: str, port: int, resolver) -> set[str]:
    resolve = resolver or socket.getaddrinfo
    try:
        infos = resolve(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:  # unresolvable host
        raise SsrfError(f"could not resolve host: {host}") from e
    return {info[4][0] for info in infos}


def assert_public_url(url: str, *, resolver=socket.getaddrinfo) -> set[str]:
    """Validate that `url` is http/https and every resolved IP is public. Returns the resolved IPs
    (so a caller could pin them). Raises SsrfError otherwise. `resolver` is injectable for tests."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SsrfError(f"scheme not allowed: {parsed.scheme or '(none)'} (only http/https)")
    host = parsed.hostname
    if not host:
        raise SsrfError("url has no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # A literal IP in the URL is judged directly; a hostname is resolved (all A/AAAA records).
    try:
        literal = ipaddress.ip_address(host)
        addrs = {str(literal)}
    except ValueError:
        addrs = _resolve(host, port, resolver)

    if not addrs:
        raise SsrfError(f"could not resolve host: {host}")
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if _ip_is_blocked(ip):
            raise SsrfError(f"blocked non-public address for {host}: {addr}")
    return addrs
