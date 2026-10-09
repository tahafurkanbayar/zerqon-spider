"""Tarama yaşam döngüsü yönetimi (bkz. ADR-003).

Her tarama ayrı bir thread'de kendi asyncio döngüsüyle çalışır; web sunucusu engellenmez.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

import httpx

from zerqon.config import Settings
from zerqon.crawler.engine import CrawlEngine, CrawlStats, Finalizer, PageAnalyzer
from zerqon.db.connection import Database
from zerqon.db.repositories import crawls_repo, projects_repo, settings_repo

logger = logging.getLogger("zerqon.crawler.manager")

MAX_PARALLEL_CRAWLS = 3
RESUMABLE_STATUSES = frozenset({"interrupted", "cancelled", "failed"})


class CrawlError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class RunningCrawl:
    crawl_id: int
    project_id: int
    thread: threading.Thread
    stop_flag: threading.Event
    stats: CrawlStats


def default_analyzer() -> PageAnalyzer | None:
    try:
        from zerqon.analysis.runner import PageAnalysisRunner
    except ImportError:
        return None
    return PageAnalysisRunner()


def default_finalizer() -> Finalizer:
    from zerqon.analysis.finalize import finalize_crawl

    return finalize_crawl


class CrawlManager:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        *,
        transport_factory: Any = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._running: dict[int, RunningCrawl] = {}
        self._lock = threading.Lock()
        self._transport_factory = transport_factory  # testlerde sahte transport için

    # ---- sorgular ----
    def is_running(self, crawl_id: int) -> bool:
        with self._lock:
            run = self._running.get(crawl_id)
            return run is not None and run.thread.is_alive()

    def progress(self, crawl_id: int) -> dict[str, Any] | None:
        with self._lock:
            run = self._running.get(crawl_id)
        return run.stats.snapshot() if run else None

    def active_ids(self) -> list[int]:
        with self._lock:
            return [cid for cid, run in self._running.items() if run.thread.is_alive()]

    # ---- komutlar ----
    def start(self, project_id: int, *, permission_confirmed: bool) -> int:
        if not permission_confirmed:
            raise CrawlError("permission_required")
        with self.db.session() as conn:
            project = projects_repo.get_project(conn, project_id)
            if project is None:
                raise CrawlError("project_not_found")
            self._check_capacity(conn, project_id)
            settings = settings_repo.get_settings(conn, project["settings_id"])
            crawl_id = crawls_repo.create_job(conn, project_id, project["start_url"], settings)
            projects_repo.touch_last_crawl(conn, project_id)
        self._launch(crawl_id, project_id, resume=False)
        return crawl_id

    def resume(self, crawl_id: int) -> None:
        with self.db.session() as conn:
            job = crawls_repo.get_job(conn, crawl_id)
            if job is None:
                raise CrawlError("crawl_not_found")
            if job["status"] not in RESUMABLE_STATUSES:
                raise CrawlError("not_resumable")
            pending = conn.execute(
                "SELECT COUNT(*) FROM frontier WHERE crawl_id = ? AND status = 'pending'", (crawl_id,)
            ).fetchone()[0]
            deferred = conn.execute(
                "SELECT COUNT(*) FROM sitemap_urls s WHERE s.crawl_id = ? AND NOT EXISTS"
                " (SELECT 1 FROM frontier f WHERE f.crawl_id = s.crawl_id AND f.url_key = s.url_key)",
                (crawl_id,),
            ).fetchone()[0]
            if pending == 0 and deferred == 0:
                raise CrawlError("nothing_to_resume")
            self._check_capacity(conn, job["project_id"])
        self._launch(crawl_id, job["project_id"], resume=True)

    def stop(self, crawl_id: int) -> bool:
        with self._lock:
            run = self._running.get(crawl_id)
        if run is None or not run.thread.is_alive():
            return False
        run.stop_flag.set()
        with self.db.session() as conn:
            crawls_repo.set_status(conn, crawl_id, "stopping")
        return True

    def shutdown(self, timeout: float = 15.0) -> None:
        with self._lock:
            runs = list(self._running.values())
        for run in runs:
            run.stop_flag.set()
        for run in runs:
            run.thread.join(timeout)

    def wait(self, crawl_id: int, timeout: float | None = None) -> None:
        with self._lock:
            run = self._running.get(crawl_id)
        if run is not None:
            run.thread.join(timeout)

    # ---- iç ----
    def _check_capacity(self, conn: Any, project_id: int) -> None:
        active = self.active_ids()
        if len(active) >= MAX_PARALLEL_CRAWLS:
            raise CrawlError("too_many_crawls")
        for cid in active:
            job = crawls_repo.get_job(conn, cid)
            if job and job["project_id"] == project_id:
                raise CrawlError("project_busy")

    def _launch(self, crawl_id: int, project_id: int, *, resume: bool) -> None:
        stop_flag = threading.Event()
        stats = CrawlStats()
        thread = threading.Thread(
            target=self._thread_main,
            args=(crawl_id, stop_flag, stats, resume),
            name=f"zerqon-crawl-{crawl_id}",
            daemon=True,
        )
        with self._lock:
            self._running[crawl_id] = RunningCrawl(crawl_id, project_id, thread, stop_flag, stats)
        thread.start()

    def _thread_main(self, crawl_id: int, stop_flag: threading.Event, stats: CrawlStats, resume: bool) -> None:
        try:
            with self.db.session() as conn:
                job = crawls_repo.get_job(conn, crawl_id)
                assert job is not None
                settings = settings_repo.get_settings(conn, job["settings_id"])
            transport: httpx.AsyncBaseTransport | None = (
                self._transport_factory() if self._transport_factory else None
            )
            engine = CrawlEngine(
                self.db,
                crawl_id,
                job["start_url"],
                settings,
                self.settings,
                stop_flag,
                stats,
                resume=resume,
                analyzer=default_analyzer(),
                finalizer=default_finalizer(),
                transport=transport,
            )
            status = asyncio.run(engine.run())
            logger.info("Tarama %s bitti: %s (%s URL)", crawl_id, status, stats.crawled)
        except Exception:  # noqa: BLE001
            logger.exception("Tarama thread'i beklenmedik şekilde sonlandı: %s", crawl_id)
            stats.status = "failed"
            try:
                with self.db.session() as conn:
                    crawls_repo.set_status(conn, crawl_id, "failed", error_code="internal_error")
            except Exception:  # noqa: BLE001
                logger.exception("Durum yazılamadı")
