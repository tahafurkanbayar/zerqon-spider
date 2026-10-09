"""Güvenlik sınırlarının aşılmadığını doğrulayan negatif testler (SSRF)."""

from __future__ import annotations

import ipaddress

import pytest

from zerqon.crawler.fetcher import Fetcher
from zerqon.crawler.security import NetworkPolicy, SecurityBlockedError, check_url, resolve_and_validate

STRICT = NetworkPolicy(allow_loopback=False)
LOCAL = NetworkPolicy(allow_loopback=True)


@pytest.mark.parametrize(
    ("ip", "reason"),
    [
        ("127.0.0.1", "loopback"),
        ("127.5.5.5", "loopback"),
        ("::1", "loopback"),
        ("10.0.0.5", "private_network"),
        ("172.16.3.4", "private_network"),
        ("192.168.1.1", "private_network"),
        ("100.64.0.1", "private_network"),
        ("169.254.169.254", "cloud_metadata"),
        ("169.254.10.10", "link_local"),
        ("fe80::1", "link_local"),
        ("fc00::1", "private_network"),
        ("0.0.0.0", "unspecified"),
        ("224.0.0.1", "multicast"),
        ("::ffff:127.0.0.1", "loopback"),
        ("::ffff:10.0.0.1", "private_network"),
        ("64:ff9b::a9fe:a9fe", "cloud_metadata"),
    ],
)
def test_blocked_addresses(ip: str, reason: str) -> None:
    assert STRICT.classify(ipaddress.ip_address(ip)) == reason


def test_public_addresses_allowed() -> None:
    assert STRICT.classify(ipaddress.ip_address("93.184.216.34")) is None
    assert STRICT.classify(ipaddress.ip_address("2606:4700::1111")) is None


def test_localhost_mode_only_opens_loopback() -> None:
    assert LOCAL.classify(ipaddress.ip_address("127.0.0.1")) is None
    assert LOCAL.classify(ipaddress.ip_address("::1")) is None
    assert LOCAL.classify(ipaddress.ip_address("192.168.1.1")) == "private_network"
    assert LOCAL.classify(ipaddress.ip_address("169.254.169.254")) == "cloud_metadata"


async def test_hostnames_and_literals_blocked() -> None:
    for url in (
        "http://localhost/",
        "http://app.localhost/",
        "http://127.0.0.1:8000/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://10.1.2.3/",
    ):
        with pytest.raises(SecurityBlockedError):
            await check_url(url, STRICT)
    with pytest.raises(SecurityBlockedError):
        await check_url("http://user:pw@example.com/", STRICT)


async def test_resolution_validates_every_address() -> None:
    # localhost birden çok adrese çözülebilir; hepsi doğrulanır
    with pytest.raises(SecurityBlockedError):
        await resolve_and_validate("localhost", 80, STRICT)
    assert await resolve_and_validate("127.0.0.1", 80, LOCAL) == ["127.0.0.1"]


async def test_fetcher_refuses_private_targets_without_network() -> None:
    fetcher = Fetcher(user_agent="test", policy=STRICT, max_retries=0, min_interval=0)
    try:
        for url in ("http://127.0.0.1:9/", "http://192.168.0.1/", "http://169.254.169.254/"):
            result = await fetcher.fetch(url)
            assert result.error_code == "blocked_security"
            assert result.status_code is None
    finally:
        await fetcher.aclose()
