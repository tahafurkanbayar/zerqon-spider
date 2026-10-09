"""Playwright ile JavaScript render (bkz. ADR-010).

- Tek Chromium örneği, `max_contexts` ile sınırlı eşzamanlı izole context.
- Ana belge isteği HTTP aşamasında alınmış ham yanıtla karşılanır (sunucuya ikinci istek yok).
- Görsel/medya/font istekleri engellenir; diğer alt istekler SSRF politikasından geçer.
- Sayfa başına zaman aşımı ve toplam render sayısı sınırı uygulanır.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from zerqon.crawler.fetcher import FetchResult
from zerqon.crawler.security import NetworkPolicy, SecurityBlockedError, check_url

logger = logging.getLogger("zerqon.crawler.renderer")

BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})
_HOP_BY_HOP = frozenset({"content-length", "content-encoding", "transfer-encoding", "connection"})


class RenderUnavailableError(Exception):
    """Chromium başlatılamadı (kurulu değil veya sistem bağımlılığı eksik)."""


@dataclass
class RenderResult:
    html: str | None
    elapsed_ms: int
    error: str | None = None
    blocked_requests: int = 0


class Renderer:
    def __init__(self, policy: NetworkPolicy, user_agent: str, timeout_s: float, max_contexts: int) -> None:
        self.policy = policy
        self.user_agent = user_agent
        self.timeout_ms = int(timeout_s * 1000)
        self._semaphore = asyncio.Semaphore(max_contexts)
        self._playwright: Any = None
        self._browser: Any = None
        self.rendered = 0

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--disable-extensions", "--disable-background-networking", "--mute-audio"],
            )
        except Exception as exc:  # noqa: BLE001 - Playwright çok çeşitli hata türleri fırlatır
            await self.close()
            raise RenderUnavailableError(str(exc).splitlines()[0][:300]) from exc

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:  # noqa: BLE001
            pass
        self._browser = self._playwright = None

    async def render(self, url: str, raw: FetchResult) -> RenderResult:
        if self._browser is None:
            return RenderResult(None, 0, "renderer_not_started")
        async with self._semaphore:
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(self._render(url, raw), timeout=self.timeout_ms / 1000 + 10)
            except TimeoutError:
                result = RenderResult(None, 0, "render_timeout")
            result.elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.rendered += 1
            return result

    async def _render(self, url: str, raw: FetchResult) -> RenderResult:
        blocked = 0
        main_served = False
        context = await self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1366, "height": 900},
            service_workers="block",
            accept_downloads=False,
            java_script_enabled=True,
        )
        context.set_default_timeout(self.timeout_ms)

        async def handle(route: Any) -> None:
            nonlocal blocked, main_served
            request = route.request
            try:
                if not main_served and request.is_navigation_request() and request.url.rstrip("/") == url.rstrip("/"):
                    main_served = True
                    headers = {k: v for k, v in raw.headers.items() if k not in _HOP_BY_HOP}
                    await route.fulfill(status=raw.status_code or 200, headers=headers, body=raw.body)
                    return
                if request.resource_type in BLOCKED_RESOURCE_TYPES:
                    blocked += 1
                    await route.abort()
                    return
                if request.is_navigation_request() and request.frame == page.main_frame:
                    # İstemci tarafı yönlendirme: tarayıcı başka sayfaya gitmeye çalışıyor; render'ı burada kes
                    blocked += 1
                    await route.abort()
                    return
                await check_url(request.url, self.policy)
                await route.continue_()
            except SecurityBlockedError:
                blocked += 1
                await route.abort()
            except Exception:  # noqa: BLE001 - kapanmış sayfa vb.
                try:
                    await route.abort()
                except Exception:  # noqa: BLE001
                    pass

        page = await context.new_page()
        try:
            await page.route("**/*", handle)
            await page.goto(url, wait_until="load", timeout=self.timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(5000, self.timeout_ms))
            except Exception:  # noqa: BLE001 - networkidle olmayabilir; mevcut DOM kullanılır
                pass
            html = await page.content()
            return RenderResult(html, 0, None, blocked)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
            logger.info("Render başarısız %s: %s", url, message)
            return RenderResult(None, 0, f"render_error: {message}", blocked)
        finally:
            try:
                await context.close()
            except Exception:  # noqa: BLE001
                pass
