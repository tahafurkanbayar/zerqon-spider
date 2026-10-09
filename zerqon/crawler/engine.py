"""Tarama motoru — robots, sitemap, kuyruk, işçiler, render, kayıt ve sonlandırma.

Akış:
  robots.txt → (sitemap keşfi) → bağlantı tabanlı BFS tarama → ertelenmiş sitemap URL'leri
  → görsel kontrolleri → sonlandırma (grafik metrikleri, indexability, site kontrolleri, puan)
Her tarama kendi thread'inde ve event loop'unda çalışır (bkz. ADR-003).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from zerqon.analysis.context import PageContext
from zerqon.config import Settings
from zerqon.crawler.fetcher import FetchResult, Fetcher
from zerqon.crawler.frontier import Frontier, FrontierItem
from zerqon.crawler.renderer import Renderer, RenderUnavailableError
from zerqon.crawler.robots import RobotsStatus, RobotsTxt, robots_url_for
from zerqon.crawler.scope import CrawlScope
from zerqon.crawler.security import NetworkPolicy
from zerqon.crawler.sitemap import MAX_SITEMAP_BYTES, SitemapKind, parse_sitemap
from zerqon.crawler.store import CrawlStore, ImageRecord, IssueRecord, LinkRecord, PageRecord
from zerqon.crawler.urls import InvalidURLError, normalize_url, resolve_url, url_key
from zerqon.db.connection import Database
from zerqon.db.repositories import crawls_repo
from zerqon.parsing.html_parser import ParsedPage, decode_html, parse_html
from zerqon.schemas import CrawlSettingsModel

logger = logging.getLogger("zerqon.crawler.engine")

FLUSH_EVERY_PAGES = 25
FLUSH_INTERVAL_S = 1.5
MAX_SITEMAP_FILES = 100
MAX_ROBOTS_REDIRECTS = 5
MAX_IMAGE_CHECKS = 5000


@dataclass
class CrawlStats:
    crawled: int = 0
    failed: int = 0
    discovered: int = 0
    issues: int = 0
    rendered: int = 0
    queued: int = 0
    last_url: str = ""
    phase: str = "starting"
    status: str = "running"
    limit_reached: bool = False
    started_at: float = field(default_factory=time.monotonic)
    _recent: deque[float] = field(default_factory=lambda: deque(maxlen=200))

    def mark_crawled(self) -> None:
        self.crawled += 1
        self._recent.append(time.monotonic())

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def rate(self) -> float:
        """Son 30 saniyedeki URL/sn."""
        now = time.monotonic()
        recent = [t for t in self._recent if now - t <= 30]
        if len(recent) < 2:
            return 0.0
        span = max(1.0, now - recent[0])
        return round(len(recent) / span, 2)

    def snapshot(self) -> dict[str, Any]:
        return {
            "crawled": self.crawled,
            "failed": self.failed,
            "queued": self.queued,
            "discovered": self.discovered,
            "issues": self.issues,
            "rendered": self.rendered,
            "last_url": self.last_url,
            "phase": self.phase,
            "status": self.status,
            "limit_reached": self.limit_reached,
            "elapsed": round(self.elapsed, 1),
            "rate": self.rate,
        }


class PageAnalyzer(Protocol):
    def analyze_page(self, ctx: PageContext) -> list[IssueRecord]: ...


Finalizer = Callable[[Any, int, CrawlSettingsModel, CrawlStore], None]


def hybrid_render_reason(raw: ParsedPage) -> str | None:
    """Hibrit modda ham HTML'in JavaScript'e bağımlı göründüğü durumlar (bkz. ADR-010)."""
    if raw.spa_root_empty:
        return "spa_root"
    if raw.word_count < 50 and raw.script_count >= 3:
        return "low_text_many_scripts"
    if raw.noscript_text and raw.word_count < 150:
        return "noscript_notice"
    if not raw.links and raw.script_count:
        return "no_links"
    return None


def _x_robots_for(values: list[str], user_agent: str) -> str:
    """Genel ve bu tarayıcıya özel X-Robots-Tag direktiflerini birleştirir; diğer botlara ait olanları atar."""
    ua = user_agent.lower()
    kept: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                head, _, rest = part.partition(":")
                if head.strip().lower() not in ("unavailable_after",) and " " not in head.strip():
                    if head.strip().lower() in ua:
                        kept.append(rest.strip())
                    continue
            kept.append(part)
    return ", ".join(kept)


class CrawlEngine:
    def __init__(
        self,
        db: Database,
        crawl_id: int,
        start_url: str,
        settings: CrawlSettingsModel,
        app_settings: Settings,
        stop_flag: threading.Event,
        stats: CrawlStats,
        *,
        resume: bool = False,
        analyzer: PageAnalyzer | None = None,
        finalizer: Finalizer | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.db = db
        self.crawl_id = crawl_id
        self.start_url = start_url
        self.settings = settings
        self.app_settings = app_settings
        self.stop_flag = stop_flag
        self.stats = stats
        self.resume = resume
        self.analyzer = analyzer
        self.finalizer = finalizer
        self.transport = transport
        self.user_agent = settings.user_agent
        self.concurrency = max(1, min(settings.concurrency, app_settings.max_concurrency))
        self.max_urls = max(1, min(settings.max_urls, app_settings.max_urls_hard_limit))
        self.policy = NetworkPolicy(allow_loopback=bool(app_settings.allow_localhost and settings.allow_localhost))
        self.scope = CrawlScope(
            start_url, settings.include_subdomains, settings.include_patterns, settings.exclude_patterns
        )
        self.frontier = Frontier(self.max_urls)
        self._robots: dict[str, RobotsTxt] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._pending: list[PageRecord] = []
        self._stopping = False
        self._last_flush = time.monotonic()
        self.renderer: Renderer | None = None
        self.conn: Any = None
        self.store: CrawlStore | None = None
        self.fetcher: Fetcher | None = None

    # ------------------------------------------------------------------ ana akış
    async def run(self) -> str:
        self.conn = self.db.connect()
        self.store = CrawlStore(self.conn, self.crawl_id)
        crawls_repo.set_status(self.conn, self.crawl_id, "running")
        if self.resume:
            crawls_repo.increment_resume(self.conn, self.crawl_id)
        self.fetcher = Fetcher(
            user_agent=self.user_agent,
            policy=self.policy,
            timeout=self.settings.timeout_seconds,
            max_retries=self.settings.max_retries,
            max_body_bytes=self.app_settings.max_body_bytes,
            min_interval=self.settings.delay_ms / 1000,
            max_connections=self.concurrency * 2,
            transport=self.transport,
        )
        watcher = asyncio.create_task(self._watch_stop())
        final_status = "completed"
        try:
            if self.settings.allow_localhost and not self.app_settings.allow_localhost:
                self.store.add_event("warning", "localhost_disabled")
            self.stats.phase = "robots"
            start_robots = await self._robots_for(self.start_url)
            delay = start_robots.crawl_delay(self.user_agent)
            if delay and delay > self.settings.delay_ms / 1000:
                self.fetcher.rate_limiter.base_interval = min(delay, 30.0)
                self.store.add_event("info", "crawl_delay_applied", f"{min(delay, 30.0):.1f}s")

            if self.resume:
                self._restore_checkpoint()
            else:
                self._enqueue(self.start_url, 0, "seed", force=True)
                if self.settings.use_sitemaps:
                    self.stats.phase = "sitemaps"
                    await self._discover_sitemaps(start_robots)

            if self.settings.render_mode != "standard" and self.settings.max_render_pages > 0:
                await self._start_renderer()

            self.stats.phase = "crawling"
            await self._crawl_loop()

            if not self._stopping and self.settings.check_images:
                self.stats.phase = "images"
                await self._check_images()

            self._flush(force=True)
            final_status = "cancelled" if self._stopping else "completed"
            self.stats.phase = "analyzing"
            if self.finalizer is not None:
                await asyncio.to_thread(self._run_finalizer)
        except Exception as exc:  # noqa: BLE001 - tarama hatası kullanıcıya raporlanır
            logger.exception("Tarama %s başarısız", self.crawl_id)
            final_status = "failed"
            try:
                self._flush(force=True)
            except Exception:  # noqa: BLE001
                logger.exception("Son flush başarısız")
            crawls_repo.set_status(
                self.conn, self.crawl_id, "failed", error_code=_error_code(exc), error_message=str(exc)[:500]
            )
        finally:
            watcher.cancel()
            if self.renderer is not None:
                await self.renderer.close()
            await self.fetcher.aclose()
            if final_status != "failed":
                self._write_progress()
                crawls_repo.set_status(self.conn, self.crawl_id, final_status)
            self.stats.status = final_status
            self.stats.phase = "done"
            self.conn.close()
        return final_status

    def _run_finalizer(self) -> None:
        assert self.finalizer is not None
        conn = self.db.connect()
        try:
            self.finalizer(conn, self.crawl_id, self.settings, CrawlStore(conn, self.crawl_id))
        finally:
            conn.close()

    async def _watch_stop(self) -> None:
        while not self.stop_flag.is_set():
            await asyncio.sleep(0.2)
        self._stopping = True
        self.stats.phase = "stopping"

    def _restore_checkpoint(self) -> None:
        assert self.store is not None
        pending, keys = self.store.load_frontier()
        self.frontier.restore(pending, keys)
        crawled, failed = self.store.count_pages()
        self.stats.crawled, self.stats.failed = crawled, failed
        self.stats.discovered = len(keys)
        rows = self.conn.execute(
            "SELECT url, url_key FROM sitemap_urls WHERE crawl_id = ?", (self.crawl_id,)
        ).fetchall()
        for row in rows:
            if row["url_key"] not in self.frontier.seen and self.scope.allows(row["url"]):
                self.frontier.defer(row["url"], row["url_key"])
        self.store.add_event("info", "resumed", f"{len(pending)}")

    # ------------------------------------------------------------------ kuyruk
    def _enqueue(self, url: str, depth: int, source: str, *, force: bool = False) -> bool:
        if not force and not self.scope.allows(url):
            return False
        if source == "link" and depth > self.settings.max_depth:
            return False
        added = self.frontier.add(url, url_key(url), depth, source)
        if added:
            self.stats.discovered += 1
        if self.frontier.limit_reached:
            self.stats.limit_reached = True
        return added

    async def _crawl_loop(self) -> None:
        workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]
        try:
            while True:
                await self._wait_for_drain()
                if self._stopping:
                    break
                if self.frontier.deferred:
                    released = self.frontier.release_deferred(depth=1)
                    self.stats.discovered += released
                    if self.frontier.limit_reached:
                        self.stats.limit_reached = True
                    if released:
                        continue
                break
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            self._flush(force=True)

    async def _wait_for_drain(self) -> None:
        join = asyncio.create_task(self.frontier.queue.join())
        while not join.done():
            done, _ = await asyncio.wait({join}, timeout=FLUSH_INTERVAL_S)
            self.stats.queued = self.frontier.queue.qsize()
            self._flush()
            if self._stopping:
                # Kuyruktaki öğeler işçiler tarafından hızla atlanır (DB'de 'pending' kalır → devam ettirilebilir)
                pass
        await join

    async def _worker(self) -> None:
        while True:
            item = await self.frontier.queue.get()
            try:
                if self._stopping:
                    continue
                record = await self._process(item)
                self._pending.append(record)
                if len(self._pending) >= FLUSH_EVERY_PAGES:
                    self._flush()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - tek sayfa hatası taramayı durdurmaz
                logger.exception("Sayfa işlenemedi: %s", item.url)
                self._pending.append(self._error_record(item, "processing_error", str(exc)[:300]))
                self.stats.failed += 1
                self.stats.mark_crawled()
            finally:
                self.frontier.queue.task_done()

    def _flush(self, force: bool = False) -> None:
        if self.store is None:
            return
        now = time.monotonic()
        if not force and len(self._pending) < FLUSH_EVERY_PAGES and now - self._last_flush < FLUSH_INTERVAL_S:
            return
        pages, self._pending = self._pending, []
        new_items = self.frontier.drain_new()
        self.store.flush(pages, new_items)
        self._last_flush = now
        self._write_progress()

    def _write_progress(self) -> None:
        crawls_repo.update_progress(
            self.conn,
            self.crawl_id,
            {
                "urls_crawled": self.stats.crawled,
                "urls_failed": self.stats.failed,
                "urls_queued": self.frontier.queue.qsize(),
                "urls_discovered": self.stats.discovered,
                "limit_reached": int(self.stats.limit_reached),
                "last_url": self.stats.last_url[:2000] or None,
            },
        )

    # ------------------------------------------------------------------ robots / sitemap
    async def _robots_for(self, url: str) -> RobotsTxt:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin not in self._robots:
                self._robots[origin] = await self._load_robots(origin)
        return self._robots[origin]

    async def _load_robots(self, origin: str) -> RobotsTxt:
        assert self.fetcher is not None and self.store is not None
        target = robots_url_for(origin + "/")
        result: FetchResult | None = None
        for _ in range(MAX_ROBOTS_REDIRECTS + 1):
            result = await self.fetcher.fetch(target, read_body=True, max_bytes=500 * 1024)
            if result.is_redirect:
                nxt = resolve_url(target, result.headers.get("location", ""))
                if not nxt:
                    break
                target = nxt
                continue
            break
        assert result is not None
        if result.error_code == "blocked_security":
            robots = RobotsTxt.disallow_all(RobotsStatus.BLOCKED)
        elif result.error_code or result.status_code is None:
            robots = RobotsTxt.disallow_all(RobotsStatus.UNAVAILABLE)
            self.store.add_event("error", "robots_unavailable", f"{origin}: {result.error_code}")
        elif 200 <= result.status_code < 300:
            robots = RobotsTxt.parse(result.text())
        elif result.status_code == 429 or result.status_code >= 500:
            robots = RobotsTxt.disallow_all(RobotsStatus.UNAVAILABLE)
            self.store.add_event("error", "robots_server_error", f"{origin}: HTTP {result.status_code}")
        else:
            robots = RobotsTxt.allow_all(RobotsStatus.NOT_FOUND)
            self.store.add_event("info", "robots_not_found", f"{origin}: HTTP {result.status_code}")
        if origin == _origin(self.start_url):
            crawls_repo.set_robots_info(self.conn, self.crawl_id, robots.status.value, robots_url_for(origin + "/"))
        return robots

    async def _discover_sitemaps(self, robots: RobotsTxt) -> None:
        assert self.fetcher is not None and self.store is not None
        queue: list[tuple[str, str, str | None]] = []
        for sm in robots.sitemaps:
            try:
                queue.append((normalize_url(sm), "robots", None))
            except InvalidURLError:
                self.store.add_event("warning", "sitemap_invalid_url", sm[:300])
        if not queue:
            queue.append((_origin(self.start_url) + "/sitemap.xml", "default", None))
        seen: set[str] = set()
        processed = 0
        total_urls = 0
        url_cap = max(self.max_urls * 10, 50_000)
        while queue and processed < MAX_SITEMAP_FILES and not self._stopping:
            sm_url, source, parent = queue.pop(0)
            if sm_url in seen:
                continue
            seen.add(sm_url)
            processed += 1
            if not self.scope.is_internal(sm_url):
                self.store.add_sitemap(sm_url, source, parent, None, None, 0, "out_of_scope", None)
                continue
            result = await self.fetcher.fetch(sm_url, read_body=True, max_bytes=MAX_SITEMAP_BYTES)
            if result.error_code:
                self.store.add_sitemap(sm_url, source, parent, None, None, 0, result.error_code, result.error_detail)
                if source != "default":
                    self.store.add_event("warning", "sitemap_fetch_failed", f"{sm_url}: {result.error_code}")
                continue
            if result.status_code is None or not 200 <= result.status_code < 300:
                self.store.add_sitemap(sm_url, source, parent, result.status_code, None, 0, "http_status", None)
                if source != "default":
                    self.store.add_event("warning", "sitemap_http_error", f"{sm_url}: HTTP {result.status_code}")
                continue
            doc = parse_sitemap(result.body)
            if doc.kind is SitemapKind.INVALID:
                self.store.add_sitemap(sm_url, source, parent, result.status_code, "invalid", 0, "invalid_xml", doc.error)
                self.store.add_event("warning", "sitemap_invalid", f"{sm_url}: {doc.error}")
                continue
            if doc.kind is SitemapKind.INDEX:
                self.store.add_sitemap(sm_url, source, parent, result.status_code, "index", len(doc.sitemaps), None, None)
                for entry in doc.sitemaps:
                    try:
                        queue.append((normalize_url(entry.loc), "index", sm_url))
                    except InvalidURLError:
                        continue
                continue
            entries: list[tuple[str, str, str | None]] = []
            for entry in doc.urls:
                if total_urls >= url_cap:
                    break
                try:
                    norm = normalize_url(entry.loc)
                except InvalidURLError:
                    continue
                entries.append((norm, url_key(norm), entry.lastmod))
                total_urls += 1
            sitemap_id = self.store.add_sitemap(
                sm_url, source, parent, result.status_code, doc.kind.value, len(entries),
                "truncated" if doc.truncated else None, None,
            )
            self.store.add_sitemap_urls(sitemap_id, entries)
            for norm, key, _ in entries:
                if self.scope.allows(norm):
                    self.frontier.defer(norm, key)
        if queue and processed >= MAX_SITEMAP_FILES:
            self.store.add_event("warning", "sitemap_limit", str(MAX_SITEMAP_FILES))

    async def _start_renderer(self) -> None:
        assert self.store is not None
        renderer = Renderer(
            self.policy,
            self.user_agent,
            timeout_s=min(self.app_settings.render_timeout_seconds, self.settings.timeout_seconds + 10),
            max_contexts=min(self.app_settings.max_render_contexts, self.concurrency),
        )
        try:
            await renderer.start()
            self.renderer = renderer
        except RenderUnavailableError as exc:
            logger.warning("Render kullanılamıyor: %s", exc)
            self.store.add_event("error", "render_unavailable", str(exc))

    # ------------------------------------------------------------------ sayfa işleme
    def _base_values(self, item: FrontierItem) -> dict[str, Any]:
        return {
            "url": item.url,
            "url_key": item.key,
            "source": item.source,
            "discovery_depth": item.depth,
            "url_length": len(item.url),
            "crawlable": 1,
            "is_html": 0,
            "body_truncated": 0,
            "rendered": 0,
            "page_nofollow": 0,
        }

    def _error_record(self, item: FrontierItem, code: str, detail: str | None) -> PageRecord:
        values = self._base_values(item)
        values.update(fetch_status="error", error_code=code, error_detail=detail)
        return PageRecord(values)

    async def _process(self, item: FrontierItem) -> PageRecord:
        assert self.fetcher is not None
        self.stats.last_url = item.url
        values = self._base_values(item)

        robots = await self._robots_for(item.url)
        if robots.status is RobotsStatus.BLOCKED:
            # Host'un kendisi güvenlik politikasıyla engelli; robots.txt sonucu değil
            values.update(fetch_status="blocked_security", error_code="blocked_security")
            self.stats.failed += 1
            self.stats.mark_crawled()
            return PageRecord(values)
        if not robots.is_allowed(item.url, self.user_agent):
            values.update(fetch_status="blocked_robots", crawlable=0)
            self.stats.mark_crawled()
            return PageRecord(values)

        result = await self.fetcher.fetch(item.url)
        self.stats.mark_crawled()
        x_robots = _x_robots_for(result.header_values("x-robots-tag"), self.user_agent)
        values.update(
            status_code=result.status_code,
            content_type=(result.content_type or "")[:200] or None,
            content_length=result.content_length,
            response_time_ms=result.elapsed_ms,
            body_truncated=int(result.truncated),
            x_robots_tag=x_robots[:500] or None,
        )
        if result.error_code:
            values.update(
                fetch_status="blocked_security" if result.error_code == "blocked_security" else "error",
                error_code=result.error_code,
                error_detail=(result.error_detail or "")[:500] or None,
            )
            self.stats.failed += 1
            return PageRecord(values)

        values["fetch_status"] = "ok"
        status = result.status_code or 0
        if status >= 400:
            self.stats.failed += 1
        if "nofollow" in x_robots.lower() or "none" in [d.strip() for d in x_robots.lower().split(",")]:
            values["page_nofollow"] = 1

        if result.is_redirect:
            target = resolve_url(item.url, result.headers.get("location", ""))
            values.update(redirect_url=target or result.headers.get("location", "")[:2000], redirect_type="http")
            if target:
                self._enqueue(target, item.depth, "redirect")
            record = PageRecord(values)
            record.issues = self._analyze(item, result, None, None, x_robots, None)
            return record

        if not (result.is_html and 200 <= status < 300):
            record = PageRecord(values)
            record.issues = self._analyze(item, result, None, None, x_robots, None)
            return record

        values["is_html"] = 1
        raw = await asyncio.to_thread(parse_html, decode_html(result.body, result.content_type), item.url)
        rendered: ParsedPage | None = None
        render_error: str | None = None
        reason = self._render_reason(raw)
        if reason and self.renderer is not None and self.renderer.rendered < self.settings.max_render_pages:
            render = await self.renderer.render(item.url, result)
            if render.html:
                rendered = await asyncio.to_thread(parse_html, render.html, item.url)
                values.update(rendered=1, render_reason=reason)
                self.stats.rendered += 1
            else:
                render_error = render.error
        effective = rendered or raw
        if "nofollow" in effective.robots_directives or "none" in effective.robots_directives:
            values["page_nofollow"] = 1

        record = PageRecord(values)
        self._collect_links(record, item, raw, rendered, effective, bool(values["page_nofollow"]))
        self._collect_extra_targets(item, effective)
        record.images = [
            ImageRecord(img, bool(img.url) and self.scope.is_internal(img.url or "")) for img in effective.images
        ]
        record.headings = effective.headings
        record.hreflang = effective.hreflang
        record.structured = effective.structured
        record.metadata = self._metadata(raw, rendered, effective, render_error)
        values.update(
            word_count=effective.word_count,
            text_hash=effective.text_hash,
            simhash=effective.simhash,
        )
        if effective.meta_refresh_url:
            values.update(redirect_url=effective.meta_refresh_url, redirect_type="meta_refresh")
            self._enqueue(effective.meta_refresh_url, item.depth, "redirect")
        record.issues = self._analyze(item, result, raw, rendered, x_robots, render_error)
        return record

    def _render_reason(self, raw: ParsedPage) -> str | None:
        if self.settings.render_mode == "javascript":
            return "javascript_mode"
        if self.settings.render_mode == "hybrid":
            return hybrid_render_reason(raw)
        return None

    def _collect_links(
        self,
        record: PageRecord,
        item: FrontierItem,
        raw: ParsedPage,
        rendered: ParsedPage | None,
        effective: ParsedPage,
        page_nofollow: bool,
    ) -> None:
        raw_targets = {link.url for link in raw.links if link.url}
        links = list(effective.links)
        if rendered is not None:
            # Render sonrası DOM'da kaybolan ham bağlantılar da kaydedilir (keşif kaybı olmasın)
            rendered_targets = {link.url for link in rendered.links if link.url}
            links += [link for link in raw.links if link.url and link.url not in rendered_targets]
        for link in links:
            internal = bool(link.url) and self.scope.is_internal(link.url or "")
            render_only = rendered is not None and bool(link.url) and link.url not in raw_targets
            record.links.append(LinkRecord(link, internal, render_only))
            if internal and link.url and not link.nofollow and not page_nofollow:
                self._enqueue(link.url, item.depth + 1, "link")

    def _collect_extra_targets(self, item: FrontierItem, effective: ParsedPage) -> None:
        canonical = effective.resolved_canonical()
        if canonical and url_key(canonical) != item.key and self.scope.is_internal(canonical):
            self._enqueue(canonical, item.depth + 1, "canonical")
        for _, href in effective.hreflang:
            target = resolve_url(effective.base_url, href)
            if target and self.scope.is_internal(target):
                self._enqueue(target, item.depth + 1, "hreflang")

    def _metadata(
        self, raw: ParsedPage, rendered: ParsedPage | None, eff: ParsedPage, render_error: str | None
    ) -> dict[str, Any]:
        canonical = eff.resolved_canonical()
        h1s = eff.h1s
        meta: dict[str, Any] = {
            "title": eff.title,
            "title_count": len(eff.titles),
            "title_length": len(eff.title) if eff.title is not None else None,
            "meta_description": eff.meta_description,
            "description_count": len(eff.meta_descriptions),
            "description_length": len(eff.meta_description) if eff.meta_description is not None else None,
            "meta_robots": ", ".join(eff.meta_robots)[:500] or None,
            "canonical": canonical,
            "canonical_key": url_key(canonical) if canonical else None,
            "canonical_count": len(eff.canonicals),
            "canonical_raw": eff.canonicals[0] if eff.canonicals else None,
            "h1": h1s[0] if h1s else None,
            "h1_count": len(h1s),
            "h2_count": sum(1 for level, _ in eff.headings if level == 2),
            "lang": (eff.lang or "")[:35] or None,
            "charset": (eff.charset or "")[:40] or None,
            "viewport": eff.viewport,
            "meta_refresh": eff.meta_refresh,
            "og_title": eff.og.get("title"),
            "og_description": eff.og.get("description"),
            "og_image": eff.og.get("image"),
            "og_url": eff.og.get("url"),
            "og_type": eff.og.get("type"),
            "twitter_card": eff.twitter.get("card"),
            "twitter_title": eff.twitter.get("title"),
            "twitter_description": eff.twitter.get("description"),
            "twitter_image": eff.twitter.get("image"),
            "hreflang_count": len(eff.hreflang),
            "structured_data_count": len(eff.structured),
            "raw_title": raw.title,
            "raw_h1": raw.h1s[0] if raw.h1s else None,
            "raw_canonical": raw.resolved_canonical(),
            "raw_meta_robots": ", ".join(raw.meta_robots)[:500] or None,
            "raw_word_count": raw.word_count,
            "raw_link_count": len(raw.links),
            "render_error": render_error,
        }
        if rendered is not None:
            raw_targets = {link.url for link in raw.links if link.url}
            meta.update(
                rendered_title=rendered.title,
                rendered_h1=rendered.h1s[0] if rendered.h1s else None,
                rendered_canonical=rendered.resolved_canonical(),
                rendered_meta_robots=", ".join(rendered.meta_robots)[:500] or None,
                rendered_word_count=rendered.word_count,
                rendered_link_count=len(rendered.links),
                render_only_links=sum(1 for link in rendered.links if link.url and link.url not in raw_targets),
            )
        return meta

    def _analyze(
        self,
        item: FrontierItem,
        result: FetchResult,
        raw: ParsedPage | None,
        rendered: ParsedPage | None,
        x_robots: str,
        render_error: str | None,
    ) -> list[IssueRecord]:
        if self.analyzer is None:
            return []
        ctx = PageContext(
            url=item.url, key=item.key, depth=item.depth, fetch=result, raw=raw, rendered=rendered,
            settings=self.settings, scope=self.scope, x_robots_tag=x_robots, render_error=render_error,
        )
        try:
            issues = self.analyzer.analyze_page(ctx)
        except Exception:  # noqa: BLE001 - analiz hatası taramayı durdurmaz
            logger.exception("Sayfa analizi başarısız: %s", item.url)
            return []
        self.stats.issues += len(issues)
        return issues

    # ------------------------------------------------------------------ görseller
    async def _check_images(self) -> None:
        assert self.fetcher is not None and self.store is not None
        rows = self.conn.execute(
            "SELECT src, src_key FROM images WHERE crawl_id = ? AND is_internal = 1"
            " AND src_key NOT IN (SELECT src_key FROM image_resources WHERE crawl_id = ?)"
            " GROUP BY src_key LIMIT ?",
            (self.crawl_id, self.crawl_id, min(MAX_IMAGE_CHECKS, self.max_urls * 3)),
        ).fetchall()
        if not rows:
            return
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        for row in rows:
            queue.put_nowait((row["src"], row["src_key"]))
        results: list[tuple[str, str, int | None, str | None, int | None, str | None]] = []

        async def worker() -> None:
            assert self.fetcher is not None
            while not queue.empty() and not self._stopping:
                src, key = queue.get_nowait()
                robots = await self._robots_for(src)
                if not robots.is_allowed(src, self.user_agent):
                    results.append((src, key, None, None, None, "blocked_robots"))
                    continue
                res = await self.fetcher.fetch(src, method="HEAD", read_body=False)
                if res.status_code in (405, 501) or (res.status_code and res.status_code >= 400 and res.status_code != 404):
                    res = await self.fetcher.fetch(src, read_body=False)
                results.append(
                    (src, key, res.status_code, (res.content_type or "")[:100] or None, res.content_length, res.error_code)
                )

        await asyncio.gather(*(worker() for _ in range(self.concurrency)))
        from zerqon.db.connection import transaction

        with transaction(self.conn):
            for src, key, status, ctype, size, error in results:
                self.store.save_image_resource(src, key, status, ctype, size, error)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _error_code(exc: BaseException) -> str:
    import sqlite3

    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        if "disk" in text and "full" in text:
            return "disk_full"
        return "database_error"
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "disk_full"
    return "internal_error"
