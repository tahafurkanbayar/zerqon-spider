"""Tarama sonlandırma hattı. Her adım idempotenttir; durdurulan/devam ettirilen taramalarda tekrar çalışır."""

from __future__ import annotations

import logging
import sqlite3

from zerqon.analysis.snapshot import save_snapshot
from zerqon.crawler.postprocess import compute_graph
from zerqon.crawler.store import CrawlStore
from zerqon.schemas import CrawlSettingsModel

logger = logging.getLogger("zerqon.analysis")


def finalize_crawl(conn: sqlite3.Connection, crawl_id: int, settings: CrawlSettingsModel, store: CrawlStore) -> None:
    logger.info("Tarama %s sonlandırılıyor", crawl_id)
    compute_graph(conn, crawl_id)
    save_snapshot(conn, crawl_id)
