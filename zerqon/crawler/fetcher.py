"""Asenkron HTTP istemcisi.

- Yönlendirmeler OTOMATİK TAKİP EDİLMEZ (ADR-005); 3xx kendi sonucu olarak döner.
- Yanıt gövdesi akışla okunur ve `max_body_bytes` ile sınırlandırılır.
- `RateLimiter` tüm işçiler arasında istek başlangıçları arasında minimum aralık uygular;
  429/503 yanıtlarında aralık geçici olarak artırılır (uyarlamalı geri çekilme).
- Ağ hataları, 429 ve 5xx için üstel geri çekilme ile sınırlı tekrar deneme.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import ssl
import time
from dataclasses import dataclass, field

import httpx

from zerqon.crawler.security import GuardedTransport, NetworkPolicy, SecurityBlockedError, check_url

logger = logging.getLogger("zerqon.crawler.fetcher")

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
BACKOFF_STATUSES = frozenset({429, 503})
MAX_RETRY_AFTER = 60.0
MAX_ADAPTIVE_DELAY = 10.0
HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass
class FetchResult:
    url: str
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    header_list: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    truncated: bool = False
    content_type: str | None = None
    content_length: int | None = None
    elapsed_ms: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.error_code is None and self.status_code is not None

    @property
    def is_html(self) -> bool:
        return bool(self.content_type) and self.content_type.split(";")[0].strip().lower() in HTML_TYPES

    @property
    def is_redirect(self) -> bool:
        return self.status_code is not None and 300 <= self.status_code < 400 and "location" in self.headers

    def header_values(self, name: str) -> list[str]:
        name = name.lower()
        return [v for k, v in self.header_list if k.lower() == name]

    def text(self) -> str:
        charset = None
        if self.content_type and "charset=" in self.content_type.lower():
            charset = self.content_type.lower().split("charset=", 1)[1].split(";")[0].strip().strip("\"'")
        for encoding in filter(None, (charset, "utf-8")):
            try:
                return self.body.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return self.body.decode("utf-8", errors="replace")


class RateLimiter:
    """İstek başlangıçları arasında paylaşılan minimum aralık + uyarlamalı geri çekilme."""

    def __init__(self, min_interval: float) -> None:
        self.base_interval = max(0.0, min_interval)
        self.penalty = 0.0
        self._next_slot = 0.0
        self._lock = asyncio.Lock()

    @property
    def interval(self) -> float:
        return self.base_interval + self.penalty

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self.interval
        if delay > 0:
            await asyncio.sleep(delay)

    def penalize(self, retry_after: float | None = None) -> None:
        self.penalty = min(MAX_ADAPTIVE_DELAY, max(self.penalty * 2, 1.0))
        if retry_after:
            self._next_slot = max(self._next_slot, time.monotonic() + min(retry_after, MAX_RETRY_AFTER))
        logger.info("Sunucu yavaşlama istedi; istek aralığı %.2f sn'ye çıkarıldı", self.interval)

    def relax(self) -> None:
        if self.penalty:
            self.penalty = max(0.0, self.penalty * 0.9 - 0.05)


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, parsed.timestamp() - time.time())


def classify_exception(exc: BaseException) -> tuple[str, str]:
    """İstisnayı kullanıcıya gösterilecek hata koduna çevirir (metinler i18n'de: errors_fetch.<kod>)."""
    if isinstance(exc, SecurityBlockedError):
        return "blocked_security", exc.reason
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", type(exc).__name__
    if isinstance(exc, httpx.ConnectError):
        text = str(exc).lower()
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, ssl.SSLError) or "ssl" in text or "certificate" in text:
            return "ssl_error", str(exc)[:200]
        if "getaddrinfo" in text or "name or service" in text or "nodename" in text or "11001" in text:
            return "dns_error", str(exc)[:200]
        if "refused" in text or "10061" in text:
            return "connection_refused", str(exc)[:200]
        return "connect_error", str(exc)[:200]
    if isinstance(exc, OSError) and ("getaddrinfo" in str(exc).lower() or "dns" in str(exc).lower()):
        return "dns_error", str(exc)[:200]
    if isinstance(exc, ssl.SSLError):
        return "ssl_error", str(exc)[:200]
    if isinstance(exc, (httpx.RemoteProtocolError, httpx.LocalProtocolError)):
        return "protocol_error", str(exc)[:200]
    if isinstance(exc, httpx.TransportError):
        return "network_error", str(exc)[:200]
    if isinstance(exc, OSError):
        return "network_error", str(exc)[:200]
    return "unknown_error", f"{type(exc).__name__}: {str(exc)[:200]}"


class Fetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        policy: NetworkPolicy,
        timeout: float = 20.0,
        max_retries: int = 2,
        max_body_bytes: int = 5 * 1024 * 1024,
        min_interval: float = 0.25,
        max_connections: int = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.policy = policy
        self.max_retries = max_retries
        self.max_body_bytes = max_body_bytes
        self.rate_limiter = RateLimiter(min_interval)
        self.client = httpx.AsyncClient(
            transport=transport or GuardedTransport(policy, max_connections=max_connections),
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "tr,en;q=0.8,*;q=0.5",
            },
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        read_body: bool | None = None,
        max_bytes: int | None = None,
        method: str = "GET",
    ) -> FetchResult:
        """`read_body=None`: gövde yalnızca HTML/XML/metin ise okunur."""
        limit = max_bytes or self.max_body_bytes
        attempts = 0
        result = FetchResult(url=url)
        try:
            await check_url(url, self.policy)
        except SecurityBlockedError as exc:
            result.error_code, result.error_detail = "blocked_security", exc.reason
            return result
        except OSError as exc:
            result.error_code, result.error_detail = classify_exception(exc)
            return result

        while True:
            attempts += 1
            await self.rate_limiter.wait()
            result = await self._attempt(url, method, read_body, limit)
            result.attempts = attempts
            retryable = result.error_code in ("timeout", "connect_error", "network_error", "protocol_error") or (
                result.status_code in RETRY_STATUSES
            )
            if result.status_code in BACKOFF_STATUSES:
                self.rate_limiter.penalize(parse_retry_after(result.headers.get("retry-after")))
            elif result.ok:
                self.rate_limiter.relax()
            if not retryable or attempts > self.max_retries:
                return result
            backoff = min(30.0, 0.5 * (2 ** (attempts - 1)))
            retry_after = parse_retry_after(result.headers.get("retry-after"))
            if retry_after is not None:
                backoff = max(backoff, min(retry_after, MAX_RETRY_AFTER))
            logger.debug("Tekrar denenecek (%s/%s) %.1fs sonra: %s", attempts, self.max_retries, backoff, url)
            await asyncio.sleep(backoff)

    async def _attempt(self, url: str, method: str, read_body: bool | None, limit: int) -> FetchResult:
        result = FetchResult(url=url)
        started = time.perf_counter()
        try:
            async with self.client.stream(method, url) as response:
                result.status_code = response.status_code
                result.header_list = [(k, v) for k, v in response.headers.multi_items()]
                result.headers = {k.lower(): v for k, v in result.header_list}
                result.content_type = response.headers.get("content-type")
                declared = response.headers.get("content-length")
                result.content_length = int(declared) if declared and declared.isdigit() else None
                main_type = (result.content_type or "").split(";")[0].strip().lower()
                should_read = read_body if read_body is not None else (
                    main_type in HTML_TYPES or "xml" in main_type or main_type.startswith("text/") or not main_type
                )
                if should_read and method != "HEAD":
                    chunks: list[bytes] = []
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > limit:
                            chunks.append(chunk[: max(0, limit - (received - len(chunk)))])
                            result.truncated = True
                            break
                        chunks.append(chunk)
                    result.body = b"".join(chunks)
                    if result.content_length is None and not result.truncated:
                        result.content_length = len(result.body)
        except SecurityBlockedError as exc:
            result.error_code, result.error_detail = "blocked_security", exc.reason
        except (httpx.HTTPError, OSError, ssl.SSLError) as exc:
            result.error_code, result.error_detail = classify_exception(exc)
        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return result
