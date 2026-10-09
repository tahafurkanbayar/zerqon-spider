"""Tarama sonlandırma hattı. Her adım idempotenttir; durdurulan/devam ettirilen taramalarda tekrar çalışır.

Sıra: grafik metrikleri → indexability → site kontrolleri → önceliklendirme → özet (snapshot)
"""

from __future__ import annotations

import logging
import sqlite3

from zerqon.analysis.context import SiteContext
from zerqon.analysis.indexability import apply_indexability
from zerqon.analysis.prioritization import prioritize
from zerqon.analysis.runner import run_site_checks
from zerqon.analysis.snapshot import save_snapshot
from zerqon.crawler.postprocess import compute_graph
from zerqon.crawler.store import CrawlStore
from zerqon.schemas import CrawlSettingsModel

logger = logging.getLogger("zerqon.analysis")


def finalize_crawl(conn: sqlite3.Connection, crawl_id: int, settings: CrawlSettingsModel, store: CrawlStore) -> None:
    logger.info("Tarama %s sonlandırılıyor", crawl_id)
    start_url = conn.execute("SELECT start_url FROM crawl_jobs WHERE id = ?", (crawl_id,)).fetchone()[0]
    compute_graph(conn, crawl_id)
    apply_indexability(conn, crawl_id)
    run_site_checks(conn, crawl_id, SiteContext(conn, crawl_id, settings, start_url), store)
    prioritize(conn, crawl_id)
    save_snapshot(conn, crawl_id)
