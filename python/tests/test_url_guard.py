"""Tests for the outbound base-URL SSRF guard (Java parity: isSafeBaseUrl)."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from knowledgeops_py.infrastructure.url_guard import (
    UnsafeBaseUrlError,
    is_safe_base_url,
    require_safe_base_url,
)


def _fake_getaddrinfo(addresses: list[str]) -> Any:
    def fake_getaddrinfo(host: str, port: int | None, **_: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0)) for address in addresses]

    return fake_getaddrinfo


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://93.184.216.34",
        "https://example.com:8443/base",
    ],
)
def test_public_urls_are_safe(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))
    assert is_safe_base_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "example.com",
        "file:///etc/passwd",
        "gopher://example.com",
        "ftp://example.com",
        "jar:file:///tmp/x",
        "http:///path",
        "http://",
        "http://example.com:notaport/",
    ],
)
def test_malformed_or_bad_scheme_urls_are_rejected(url: str) -> None:
    assert is_safe_base_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8500",
        "http://localhost",
        "http://LOCALHOST:11434",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://[::]/",
        "http://224.0.0.1/",
        "http://[::ffff:127.0.0.1]/",
        "http://100.64.0.1/",
    ],
)
def test_internal_addresses_are_rejected(url: str) -> None:
    assert is_safe_base_url(url) is False


def test_dns_resolving_to_private_address_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["10.0.0.5", "93.184.216.34"]))
    assert is_safe_base_url("https://internal.example.com") is False


def test_dns_resolving_to_public_address_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))
    assert is_safe_base_url("https://api.example.com") is True


def test_dns_resolution_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_getaddrinfo(host: str, port: int | None, **_: Any) -> list[tuple[Any, ...]]:
        raise socket.gaierror(8, "nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", failing_getaddrinfo)
    assert is_safe_base_url("https://unresolvable.example.com") is False


def test_require_safe_base_url_returns_url_or_raises() -> None:
    assert require_safe_base_url("https://example.com", setting="web search") == "https://example.com"
    with pytest.raises(UnsafeBaseUrlError, match="SSRF safety guard"):
        require_safe_base_url("http://169.254.169.254/", setting="metadata")
