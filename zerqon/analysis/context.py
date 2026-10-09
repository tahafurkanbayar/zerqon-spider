"""Analiz kontrollerinin girdileri."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlsplit

from zerqon.crawler.fetcher import FetchResult
from zerqon.crawler.scope import CrawlScope
from zerqon.parsing.html_parser import ParsedPage
from zerqon.schemas import CrawlSettingsModel


@dataclass
class PageContext:
    """Sayfa düzeyi kontroller için girdi (tarama sırasında, bellekteki veriden)."""

    url: str
    key: str
    depth: int
    fetch: FetchResult
    raw: ParsedPage | None
    rendered: ParsedPage | None
    settings: CrawlSettingsModel
    scope: CrawlScope
    x_robots_tag: str
    render_error: str | None = None

    @property
    def effective(self) -> ParsedPage | None:
        return self.rendered or self.raw

    @property
    def is_html_ok(self) -> bool:
        status = self.fetch.status_code or 0
        return self.effective is not None and 200 <= status < 300

    @property
    def scheme(self) -> str:
        return urlsplit(self.url).scheme


@dataclass
class SiteContext:
    """Site düzeyi kontroller için girdi (tarama sonunda, veritabanından)."""

    conn: sqlite3.Connection
    crawl_id: int
    settings: CrawlSettingsModel
    start_url: str

    @property
    def start_scheme(self) -> str:
        return urlsplit(self.start_url).scheme
