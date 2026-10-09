"""Tarama verilerinin SQLite'a toplu yazımı.

Her flush tek bir işlemdir: sayfalar + alt kayıtları + frontier durumu birlikte yazılır.
Böylece çökme sonrası devam ettirmede yarım kayıt oluşmaz (bkz. ADR-004).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from zerqon.crawler.frontier import FrontierItem
from zerqon.crawler.urls import url_key
from zerqon.db.connection import transaction, utcnow_iso
from zerqon.parsing.html_parser import ImageData, LinkData
from zerqon.parsing.structured_data import StructuredItem

PAGE_COLUMNS: tuple[str, ...] = (
    "url", "url_key", "source", "discovery_depth", "fetch_status", "status_code", "content_type",
    "content_length", "response_time_ms", "is_html", "body_truncated", "redirect_url", "redirect_type",
    "error_code", "error_detail", "x_robots_tag", "crawlable", "page_nofollow", "rendered", "render_reason",
    "url_length", "word_count", "text_hash", "simhash",
)

META_COLUMNS: tuple[str, ...] = (
    "title", "title_count", "title_length", "meta_description", "description_count", "description_length",
    "meta_robots", "canonical", "canonical_key", "canonical_count", "canonical_raw", "h1", "h1_count", "h2_count",
    "lang", "charset", "viewport", "meta_refresh", "og_title", "og_description", "og_image", "og_url", "og_type",
    "twitter_card", "twitter_title", "twitter_description", "twitter_image", "hreflang_count",
    "structured_data_count", "raw_title", "rendered_title", "raw_h1", "rendered_h1", "raw_canonical",
    "rendered_canonical", "raw_meta_robots", "rendered_meta_robots", "raw_word_count", "rendered_word_count",
    "raw_link_count", "rendered_link_count", "render_only_links", "render_error",
)


@dataclass
class LinkRecord:
    link: LinkData
    is_internal: bool
    render_only: bool = False


@dataclass
class ImageRecord:
    image: ImageData
    is_internal: bool


@dataclass
class IssueRecord:
    code: str
    category: str
    severity: str
    evidence: str | None = None
    signals: str | None = None


@dataclass
class PageRecord:
    values: dict[str, Any]
    metadata: dict[str, Any] | None = None
    headings: list[tuple[int, str]] = field(default_factory=list)
    links: list[LinkRecord] = field(default_factory=list)
    images: list[ImageRecord] = field(default_factory=list)
    hreflang: list[tuple[str, str]] = field(default_factory=list)
    structured: list[StructuredItem] = field(default_factory=list)
    issues: list[IssueRecord] = field(default_factory=list)

    @property
    def key(self) -> str:
        return str(self.values["url_key"])


SEVERITY_RANK: dict[str, int] = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}


class CrawlStore:
    def __init__(self, conn: sqlite3.Connection, crawl_id: int) -> None:
        self.conn = conn
        self.crawl_id = crawl_id

    # ---- frontier / checkpoint ----
    def load_frontier(self) -> tuple[list[tuple[str, str, int, str]], set[str]]:
        rows = self.conn.execute(
            "SELECT url, url_key, depth, source, status FROM frontier WHERE crawl_id = ? ORDER BY depth, id",
            (self.crawl_id,),
        ).fetchall()
        pending = [(r["url"], r["url_key"], r["depth"], r["source"]) for r in rows if r["status"] == "pending"]
        return pending, {r["url_key"] for r in rows}

    def count_pages(self) -> tuple[int, int]:
        row = self.conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN fetch_status IN ('error','blocked_security') OR status_code >= 400"
            " THEN 1 ELSE 0 END) FROM pages WHERE crawl_id = ?",
            (self.crawl_id,),
        ).fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    # ---- toplu yazım ----
    def flush(self, pages: list[PageRecord], new_frontier: list[FrontierItem]) -> None:
        if not pages and not new_frontier:
            return
        now = utcnow_iso()
        with transaction(self.conn):
            if new_frontier:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO frontier(crawl_id, url, url_key, depth, source) VALUES (?, ?, ?, ?, ?)",
                    [(self.crawl_id, i.url, i.key, i.depth, i.source) for i in new_frontier],
                )
            for record in pages:
                self._insert_page(record, now)
            if pages:
                self.conn.executemany(
                    "UPDATE frontier SET status = 'done' WHERE crawl_id = ? AND url_key = ?",
                    [(self.crawl_id, r.key) for r in pages],
                )

    def _insert_page(self, record: PageRecord, now: str) -> None:
        values = record.values
        cols = list(PAGE_COLUMNS)
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO pages(crawl_id, fetched_at, {', '.join(cols)})"  # noqa: S608 - sabit sütunlar
            f" VALUES (?, ?, {', '.join('?' for _ in cols)})",
            [self.crawl_id, now, *[values.get(c) for c in cols]],
        )
        if cur.rowcount == 0:
            return  # zaten yazılmış (devam ettirme)
        page_id = int(cur.lastrowid or 0)
        if record.metadata is not None:
            mcols = [c for c in META_COLUMNS if c in record.metadata]
            self.conn.execute(
                f"INSERT INTO page_metadata(page_id, {', '.join(mcols)}) VALUES (?, {', '.join('?' for _ in mcols)})",  # noqa: S608
                [page_id, *[record.metadata[c] for c in mcols]],
            )
        if record.headings:
            self.conn.executemany(
                "INSERT INTO headings(page_id, position, level, text) VALUES (?, ?, ?, ?)",
                [(page_id, i, lvl, text) for i, (lvl, text) in enumerate(record.headings)],
            )
        if record.links:
            self.conn.executemany(
                "INSERT INTO links(crawl_id, source_page_id, target_url, target_key, anchor_text, rel, nofollow,"
                " is_internal, render_only, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        self.crawl_id, page_id, lr.link.url or lr.link.href, url_key(lr.link.url or lr.link.href),
                        lr.link.anchor, lr.link.rel or None, int(lr.link.nofollow), int(lr.is_internal),
                        int(lr.render_only), i,
                    )
                    for i, lr in enumerate(record.links)
                ],
            )
        if record.images:
            self.conn.executemany(
                "INSERT INTO images(crawl_id, page_id, src, src_key, alt, alt_present, width, height, loading,"
                " has_srcset, is_internal, decorative) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        self.crawl_id, page_id, ir.image.url or ir.image.src, url_key(ir.image.url or ir.image.src),
                        ir.image.alt, int(ir.image.alt is not None), ir.image.width, ir.image.height,
                        ir.image.loading, int(ir.image.has_srcset), int(ir.is_internal), int(ir.image.decorative),
                    )
                    for ir in record.images
                ],
            )
        if record.hreflang:
            self.conn.executemany(
                "INSERT INTO hreflang(page_id, lang, href, href_key) VALUES (?, ?, ?, ?)",
                [(page_id, lang, href, url_key(href)) for lang, href in record.hreflang],
            )
        if record.structured:
            self.conn.executemany(
                "INSERT INTO structured_data(page_id, format, schema_type, valid, error, missing_fields)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (page_id, s.format, s.schema_type, int(s.valid), s.error, ",".join(s.missing_fields) or None)
                    for s in record.structured
                ],
            )
        if record.issues:
            self.insert_issues(
                [(page_id, values["url"], record.key, issue) for issue in record.issues], now
            )

    def insert_issues(self, rows: list[tuple[int | None, str | None, str | None, IssueRecord]], now: str | None = None) -> None:
        now = now or utcnow_iso()
        self.conn.executemany(
            "INSERT INTO issues(crawl_id, page_id, url, url_key, code, category, base_severity, severity,"
            " severity_rank, evidence, signals, detected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    self.crawl_id, page_id, url, key, issue.code, issue.category, issue.severity, issue.severity,
                    SEVERITY_RANK[issue.severity], issue.evidence, issue.signals, now,
                )
                for page_id, url, key, issue in rows
            ],
        )

    # ---- sitemap / robots / olaylar ----
    def add_sitemap(
        self, url: str, source: str, parent: str | None, status: int | None, kind: str | None,
        count: int, error_code: str | None, error_detail: str | None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO sitemaps(crawl_id, url, source, parent_url, status_code, kind, url_count, error_code,"
            " error_detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.crawl_id, url, source, parent, status, kind, count, error_code, error_detail),
        )
        return int(cur.lastrowid or 0)

    def add_sitemap_urls(self, sitemap_id: int, entries: list[tuple[str, str, str | None]]) -> None:
        with transaction(self.conn):
            self.conn.executemany(
                "INSERT OR IGNORE INTO sitemap_urls(crawl_id, sitemap_id, url, url_key, lastmod) VALUES (?, ?, ?, ?, ?)",
                [(self.crawl_id, sitemap_id, url, key, lastmod) for url, key, lastmod in entries],
            )

    def add_event(self, level: str, code: str, detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO crawl_events(crawl_id, created_at, level, code, detail) VALUES (?, ?, ?, ?, ?)",
            (self.crawl_id, utcnow_iso(), level, code, (detail or "")[:1000] or None),
        )

    def save_image_resource(
        self, url: str, key: str, status: int | None, content_type: str | None, size: int | None, error: str | None
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO image_resources(crawl_id, url, src_key, status_code, content_type, size_bytes,"
            " error_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.crawl_id, url, key, status, content_type, size, error),
        )
