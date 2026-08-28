"""Outbound base-URL safety guard (Java parity: HttpMcpToolAdapter.isSafeBaseUrl).

Rejects base URLs whose scheme or resolved addresses point at loopback,
private, link-local, multicast, reserved or unspecified networks so that an
operator misconfiguration or an LLM-driven tool call can never make the
service reach internal endpoints (cloud metadata, localhost services).

Fail-closed: any parsing or DNS-resolution error rejects the URL. Stricter
than the Java guard on purpose: Python's ``is_private`` also rejects
CGNAT (100.64/10) and other non-global ranges.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")

# Address ranges Python's is_private does not cover but that must never be
# reached from a server-side fetch (CGNAT shared address space).
_EXTRA_FORBIDDEN_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"),)


class UnsafeBaseUrlError(ValueError):
    """Raised when a base URL fails the SSRF safety guard."""


def _address_is_forbidden(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return True
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    if any(parsed in network for network in _EXTRA_FORBIDDEN_NETWORKS):
        return True
    return (
        parsed.is_unspecified
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_private
    )


def is_safe_base_url(url: str) -> bool:
    """Return True only when ``url`` is a fetchable, non-internal base URL."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ALLOWED_SCHEMES or not parts.hostname:
            return False
        infos = socket.getaddrinfo(parts.hostname, parts.port, proto=socket.IPPROTO_TCP)
    except (ValueError, UnicodeError, socket.gaierror, OSError):
        return False
    if not infos:
        return False
    return all(not _address_is_forbidden(str(info[4][0])) for info in infos)


def require_safe_base_url(url: str, *, setting: str = "base url") -> str:
    """Validate ``url`` and return it, or raise :class:`UnsafeBaseUrlError`."""
    if not is_safe_base_url(url):
        raise UnsafeBaseUrlError(f"{setting} failed the SSRF safety guard")
    return url
