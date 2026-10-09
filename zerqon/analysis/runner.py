"""Kontrolleri çalıştıran giriş noktaları."""

from __future__ import annotations

import logging
import sqlite3

from zerqon.analysis.context import PageContext, SiteContext
from zerqon.analysis.issues import REGISTRY, SITE_CODES
from zerqon.analysis.registry import PAGE_CHECKS, SITE_CHECKS, SiteIssue, load_checks
from zerqon.crawler.store import CrawlStore, IssueRecord
from zerqon.db.connection import transaction

logger = logging.getLogger("zerqon.analysis")


class PageAnalysisRunner:
    """Tarama sırasında her sayfa için kayıtlı sayfa kontrollerini çalıştırır."""

    def __init__(self) -> None:
        load_checks()

    def analyze_page(self, ctx: PageContext) -> list[IssueRecord]:
        found: list[IssueRecord] = []
        for check in PAGE_CHECKS:
            try:
                found.extend(check(ctx))
            except Exception:  # noqa: BLE001 - tek kontrolün hatası diğerlerini durdurmaz
                logger.exception("Sayfa kontrolü başarısız: %s (%s)", check.__name__, ctx.url)
        return found


def run_site_checks(conn: sqlite3.Connection, crawl_id: int, ctx: SiteContext, store: CrawlStore) -> int:
    """Site kontrollerini idempotent çalıştırır: önceki site sorunları silinip yeniden üretilir."""
    load_checks()
    placeholders = ", ".join("?" for _ in SITE_CODES)
    results: list[SiteIssue] = []
    for check in SITE_CHECKS:
        try:
            results.extend(check(ctx))
        except Exception:  # noqa: BLE001
            logger.exception("Site kontrolü başarısız: %s", check.__name__)
    for _, _, _, record in results:
        assert REGISTRY[record.code].scope == "site", record.code
    with transaction(conn):
        conn.execute(
            f"DELETE FROM issues WHERE crawl_id = ? AND code IN ({placeholders})",  # noqa: S608
            (crawl_id, *SITE_CODES),
        )
        # Engellenen sayfalar için bilgi kaydı (tarama sırasında içerik yok)
        conn.execute("DELETE FROM issues WHERE crawl_id = ? AND code = 'blocked_by_robots'", (crawl_id,))
        store.insert_issues(results)
        blocked = conn.execute(
            "SELECT id, url, url_key FROM pages WHERE crawl_id = ? AND fetch_status = 'blocked_robots'", (crawl_id,)
        ).fetchall()
        from zerqon.analysis.issues import issue

        store.insert_issues([(r["id"], r["url"], r["url_key"], issue("blocked_by_robots", "robots.txt")) for r in blocked])
    return len(results) + len(blocked)
