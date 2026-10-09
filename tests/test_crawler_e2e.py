"""Tarama motorunun yerel test sitesine karşı uçtan uca testleri."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from zerqon.analysis.finalize import finalize_crawl
from zerqon.analysis.runner import PageAnalysisRunner
from zerqon.config import Settings
from zerqon.crawler.engine import CrawlEngine, CrawlStats
from zerqon.db.connection import Database
from zerqon.db.repositories import crawls_repo, projects_repo
from zerqon.schemas import CrawlSettingsModel, ProjectCreate
from tests.fixtures.site import serve_site


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with serve_site() as base:
        yield base


def run_crawl(
    db: Database,
    app_settings: Settings,
    base: str,
    *,
    stop_after: int | None = None,
    resume_id: int | None = None,
    **overrides: Any,
) -> tuple[int, str, CrawlStats]:
    params: dict[str, Any] = {"allow_localhost": True, "delay_ms": 0, "concurrency": 4, "max_retries": 1}
    params.update(overrides)
    settings = CrawlSettingsModel(**params)
    with db.session() as conn:
        if resume_id is None:
            pid = projects_repo.create_project(conn, ProjectCreate(name="Test", start_url=base + "/"), settings)
            crawl_id = crawls_repo.create_job(conn, pid, base + "/", settings)
        else:
            crawl_id = resume_id
    stop = threading.Event()
    stats = CrawlStats()

    import asyncio

    engine = CrawlEngine(
        db, crawl_id, base + "/", settings, app_settings, stop, stats,
        resume=resume_id is not None, finalizer=finalize_crawl, analyzer=PageAnalysisRunner(),
    )
    if stop_after is not None:
        def watcher() -> None:
            import time

            while stats.crawled < stop_after and stats.phase not in ("done", "analyzing"):
                time.sleep(0.01)
            stop.set()

        threading.Thread(target=watcher, daemon=True).start()
    status = asyncio.run(engine.run())
    return crawl_id, status, stats


def pages_by_path(conn: sqlite3.Connection, crawl_id: int, base: str) -> dict[str, sqlite3.Row]:
    rows = conn.execute("SELECT * FROM pages WHERE crawl_id = ?", (crawl_id,)).fetchall()
    return {row["url"].replace(base, ""): row for row in rows}


def test_full_crawl(db: Database, settings: Settings, site: str) -> None:
    crawl_id, status, stats = run_crawl(db, settings, site, check_images=True)
    assert status == "completed"
    with db.session() as conn:
        pages = pages_by_path(conn, crawl_id, site)
        job = crawls_repo.get_job(conn, crawl_id)
        assert job is not None and job["status"] == "completed" and job["robots_status"] == "ok"

        # Temel keşif
        assert pages["/"]["status_code"] == 200 and pages["/"]["source"] == "seed"
        assert pages["/about"]["status_code"] == 200
        assert pages["/broken"]["status_code"] == 404
        assert pages["/error"]["status_code"] == 500

        # robots.txt engeli: istek gönderilmez
        assert pages["/private/secret"]["fetch_status"] == "blocked_robots"
        assert pages["/private/secret"]["status_code"] is None

        # nofollow bağlantı takip edilmez, dış alan adı asla taranmaz
        assert "/nofollow-target" not in pages
        assert not any("external.example" in url for url in pages)
        external = conn.execute(
            "SELECT COUNT(*) FROM links WHERE crawl_id = ? AND is_internal = 0", (crawl_id,)
        ).fetchone()[0]
        assert external >= 1

        # Sitemap: index → gzip urlset; yalnız sitemap'te olan sayfa da taranır
        assert pages["/orphan"]["source"] == "sitemap"
        assert pages["/orphan"]["in_sitemap"] == 1
        assert pages["/orphan"]["inlinks"] == 0
        assert pages["/orphan"]["crawl_depth"] is None
        kinds = {r["kind"] for r in conn.execute("SELECT kind FROM sitemaps WHERE crawl_id = ?", (crawl_id,))}
        assert {"index", "urlset"} <= kinds

        # Yönlendirme zinciri ve döngü
        chain = conn.execute(
            "SELECT hop, from_url, to_url, status_code FROM redirects WHERE page_id = ? ORDER BY hop",
            (pages["/redirect-1"]["id"],),
        ).fetchall()
        assert [r["status_code"] for r in chain] == [301, 302]
        assert chain[-1]["to_url"].endswith("/about")
        loop = conn.execute(
            "SELECT COUNT(*) FROM redirects WHERE page_id = ?", (pages["/loop-a"]["id"],)
        ).fetchone()[0]
        assert loop == 2

        # Meta veriler, X-Robots-Tag, inlink ve derinlik
        meta = conn.execute("SELECT * FROM page_metadata WHERE page_id = ?", (pages["/"]["id"],)).fetchone()
        assert meta["title"] == "Ana Sayfa | Örnek Site"
        assert meta["h1"] == "Hoş geldiniz"
        assert meta["canonical"] == site + "/"
        assert pages["/xrobots"]["x_robots_tag"] == "noindex"
        assert pages["/about"]["inlinks"] == 1 and pages["/"]["inlinks"] >= 2
        assert pages["/"]["crawl_depth"] == 0
        assert pages["/about"]["crawl_depth"] == 1
        assert pages["/deep/1"]["crawl_depth"] == 1

        # Görsel kontrolleri
        images = {
            r["url"].replace(site, ""): r
            for r in conn.execute("SELECT * FROM image_resources WHERE crawl_id = ?", (crawl_id,))
        }
        assert images["/img/logo.png"]["status_code"] == 200
        assert images["/img/missing.png"]["status_code"] == 404
        assert images["/img/big.jpg"]["size_bytes"] > 200_000

        snapshot = crawls_repo.get_snapshot(conn, crawl_id)
        assert snapshot is not None and snapshot["pages_total"] == len(pages)
        assert snapshot["status_4xx"] >= 1 and snapshot["status_5xx"] >= 1


def test_max_urls_never_exceeded(db: Database, settings: Settings, site: str) -> None:
    crawl_id, status, stats = run_crawl(db, settings, site, max_urls=5, use_sitemaps=False, check_images=False)
    with db.session() as conn:
        count = conn.execute("SELECT COUNT(*) FROM pages WHERE crawl_id = ?", (crawl_id,)).fetchone()[0]
        job = crawls_repo.get_job(conn, crawl_id)
    assert status == "completed"
    assert count == 5
    assert job is not None and job["limit_reached"] == 1


def test_max_depth_respected(db: Database, settings: Settings, site: str) -> None:
    crawl_id, _, _ = run_crawl(db, settings, site, max_depth=2, use_sitemaps=False, check_images=False)
    with db.session() as conn:
        paths = set(pages_by_path(conn, crawl_id, site))
    assert "/deep/1" in paths and "/deep/2" in paths
    assert "/deep/3" not in paths


def test_exclude_patterns(db: Database, settings: Settings, site: str) -> None:
    crawl_id, _, _ = run_crawl(
        db, settings, site, exclude_patterns=r"/deep/" + "\n" + r"/about", use_sitemaps=False, check_images=False
    )
    with db.session() as conn:
        paths = set(pages_by_path(conn, crawl_id, site))
    assert not any(p.startswith("/deep/") or p.startswith("/about") for p in paths)


def test_localhost_blocked_without_mode(db: Database, settings: Settings, site: str) -> None:
    strict = Settings(_env_file=None, data_dir=settings.data_dir, allow_localhost=False)  # type: ignore[call-arg]
    crawl_id, status, _ = run_crawl(db, strict, site, use_sitemaps=False, check_images=False)
    with db.session() as conn:
        rows = conn.execute("SELECT fetch_status, error_code FROM pages WHERE crawl_id = ?", (crawl_id,)).fetchall()
        job = crawls_repo.get_job(conn, crawl_id)
    assert status == "completed"
    assert len(rows) == 1
    assert rows[0]["fetch_status"] == "blocked_security"
    assert job is not None and job["robots_status"] == "blocked_security"


def test_stop_and_resume(db: Database, settings: Settings, site: str) -> None:
    crawl_id, status, stats = run_crawl(
        db, settings, site, stop_after=3, concurrency=1, use_sitemaps=False, check_images=False
    )
    assert status == "cancelled"
    with db.session() as conn:
        first = conn.execute("SELECT COUNT(*) FROM pages WHERE crawl_id = ?", (crawl_id,)).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM frontier WHERE crawl_id = ? AND status = 'pending'", (crawl_id,)
        ).fetchone()[0]
        assert crawls_repo.get_snapshot(conn, crawl_id) is not None  # kısmi veri korunur ve özetlenir
    assert first >= 3 and pending > 0

    _, status2, _ = run_crawl(
        db, settings, site, resume_id=crawl_id, concurrency=1, use_sitemaps=False, check_images=False
    )
    assert status2 == "completed"
    with db.session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM pages WHERE crawl_id = ?", (crawl_id,)).fetchone()[0]
        dupes = conn.execute(
            "SELECT COUNT(*) FROM (SELECT url_key FROM pages WHERE crawl_id = ? GROUP BY url_key HAVING COUNT(*) > 1)",
            (crawl_id,),
        ).fetchone()[0]
        job = crawls_repo.get_job(conn, crawl_id)
    assert total > first
    assert dupes == 0
    assert job is not None and job["resume_count"] == 1


def test_429_backoff_and_retry(db: Database, settings: Settings, site: str) -> None:
    import asyncio

    from zerqon.crawler.fetcher import Fetcher
    from zerqon.crawler.security import NetworkPolicy

    async def go() -> tuple[int | None, int, float]:
        fetcher = Fetcher(user_agent="t", policy=NetworkPolicy(allow_loopback=True), max_retries=2, min_interval=0)
        try:
            res = await fetcher.fetch(site + "/throttled")
            return res.status_code, res.attempts, fetcher.rate_limiter.penalty
        finally:
            await fetcher.aclose()

    status, attempts, penalty = asyncio.run(go())
    assert status == 200
    assert attempts == 2
    assert penalty > 0  # 429 sonrası istek aralığı artırıldı


def test_issues_and_prioritization(db: Database, settings: Settings, site: str) -> None:
    crawl_id, status, _ = run_crawl(db, settings, site, check_images=True)
    assert status == "completed"
    with db.session() as conn:
        rows = conn.execute(
            "SELECT i.code, i.severity, i.base_severity, i.evidence, p.url FROM issues i"
            " LEFT JOIN pages p ON p.id = i.page_id WHERE i.crawl_id = ?",
            (crawl_id,),
        ).fetchall()
        by_code: dict[str, list[sqlite3.Row]] = {}
        for r in rows:
            by_code.setdefault(r["code"], []).append(r)
        for expected in (
            "broken_internal_link", "redirect_chain", "redirect_loop", "status_4xx", "status_5xx",
            "orphan_candidate", "sitemap_url_noindex", "title_duplicate", "structured_data_syntax_error",
            "image_broken", "image_too_large", "blocked_by_robots", "internal_link_to_redirect",
        ):
            assert expected in by_code, expected
        # Kanıt dolu olmalı
        assert all(r["evidence"] for r in by_code["broken_internal_link"])
        # Sitemap'teki önemli sayfada noindex → high (muhtemelen istenmeyen)
        noindex = {r["url"].replace(site, ""): r["severity"] for r in by_code["noindex"]}
        assert noindex["/noindex-page"] == "high"
        assert noindex["/xrobots"] == "info"
        # Indexlenemeyen sayfada meta sorunu bir seviye düşer
        canon_desc = [r for r in by_code.get("description_missing", []) if r["url"].endswith("/canonical-other")]
        assert canon_desc and canon_desc[0]["severity"] == "low"
        # Sayfa sorun sayıları hesaplanmış
        home = conn.execute(
            "SELECT issues_count FROM pages WHERE crawl_id = ? AND url = ?", (crawl_id, site + "/")
        ).fetchone()
        assert home["issues_count"] >= 1
