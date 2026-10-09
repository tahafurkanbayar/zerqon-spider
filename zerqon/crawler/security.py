"""SSRF koruması (bkz. ADR-006).

Kontrol iki katmanlıdır:
1. `check_url()` — istek öncesi hızlı ve anlaşılır doğrulama.
2. `GuardedNetworkBackend` — bağlantı anında DNS çözümlemesi + IP doğrulaması yapar ve
   doğrulanmış IP'ye bağlanır. Böylece DNS-rebinding ile kontrol atlatılamaz.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Bulut sağlayıcı metadata servisleri — localhost modunda bile her zaman engelli
METADATA_ADDRESSES: frozenset[IPAddress] = frozenset(
    ipaddress.ip_address(a)
    for a in ("169.254.169.254", "169.254.170.2", "100.100.100.200", "fd00:ec2::254", "192.0.0.192")
)
LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")
LOOPBACK_V6 = ipaddress.ip_address("::1")
NAT64 = ipaddress.ip_network("64:ff9b::/96")
METADATA_HOSTNAMES: frozenset[str] = frozenset({"metadata.google.internal", "metadata", "instance-data"})


class SecurityBlockedError(Exception):
    """Hedef adres güvenlik politikası tarafından engellendi."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class NetworkPolicy:
    """allow_loopback yalnızca localhost modu açıkken True olur."""

    allow_loopback: bool = False

    def classify(self, ip: IPAddress) -> str | None:
        """Engelleme nedenini döndürür; izinliyse None."""
        if isinstance(ip, ipaddress.IPv6Address):
            if ip.ipv4_mapped is not None:
                return self.classify(ip.ipv4_mapped)
            if ip in NAT64:
                return self.classify(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if ip in METADATA_ADDRESSES:
            return "cloud_metadata"
        is_loopback = ip == LOOPBACK_V6 or (isinstance(ip, ipaddress.IPv4Address) and ip in LOOPBACK_V4)
        if is_loopback:
            return None if self.allow_loopback else "loopback"
        if ip.is_unspecified:
            return "unspecified"
        if ip.is_link_local:
            return "link_local"
        if ip.is_multicast:
            return "multicast"
        if ip.is_private or not ip.is_global:
            return "private_network"
        return None

    def check_ip(self, ip: IPAddress) -> None:
        reason = self.classify(ip)
        if reason:
            raise SecurityBlockedError(reason, str(ip))

    def check_hostname(self, host: str) -> None:
        host = host.lower().rstrip(".")
        if host in METADATA_HOSTNAMES:
            raise SecurityBlockedError("cloud_metadata", host)
        if (host == "localhost" or host.endswith(".localhost")) and not self.allow_loopback:
            raise SecurityBlockedError("loopback", host)


def _literal_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


async def resolve_and_validate(host: str, port: int, policy: NetworkPolicy) -> list[str]:
    """Host'u çözer, TÜM adresleri doğrular (biri bile yasaksa engeller), IP listesini döndürür."""
    policy.check_hostname(host)
    literal = _literal_ip(host)
    if literal is not None:
        policy.check_ip(literal)
        return [str(literal)]
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for family, *_rest, sockaddr in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        ip = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
        policy.check_ip(ip)
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise OSError(f"DNS çözümlemesi sonuç vermedi: {host}")
    return addresses


async def check_url(url: str, policy: NetworkPolicy) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise SecurityBlockedError("scheme", parts.scheme)
    if parts.username or parts.password:
        raise SecurityBlockedError("credentials_in_url")
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    await resolve_and_validate(host, port, policy)


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Her TCP bağlantısında IP politikasını uygulayan httpcore ağ katmanı."""

    def __init__(self, policy: NetworkPolicy) -> None:
        self._policy = policy
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await resolve_and_validate(host, port, self._policy)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    address, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore.AsyncNetworkStream:
        raise SecurityBlockedError("unix_socket", path)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class GuardedTransport(httpx.AsyncHTTPTransport):
    """Proxy kullanmayan (trust_env=False), SSRF korumalı httpx transport."""

    def __init__(self, policy: NetworkPolicy, *, verify: bool = True, max_connections: int = 20) -> None:
        super().__init__(verify=verify, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=verify, trust_env=False),
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            keepalive_expiry=15.0,
            http1=True,
            http2=False,
            network_backend=GuardedNetworkBackend(policy),
        )
