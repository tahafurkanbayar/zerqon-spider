"""CSV dışa aktarma.

- UTF-8 + BOM (Excel'de Türkçe karakterler doğru görünür).
- CSV/formula injection koruması: `= + - @ \\t \\r` ile başlayan hücrelerin başına `'` eklenir (OWASP önerisi).
- Büyük veri için satırlar akış halinde üretilir.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from zerqon.db.repositories.pages_repo import PageQuery, iter_pages

BOM = "﻿"
_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_NUMERIC_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def safe_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.startswith(_DANGEROUS_PREFIXES) and not _NUMERIC_RE.match(text):
        return "'" + text
    return text


def rows_to_csv(header: list[str], rows: Iterable[Iterable[Any]]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    yield BOM
    writer.writerow([safe_cell(h) for h in header])
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
        if buffer.tell() > 64 * 1024:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
    yield buffer.getvalue()


@dataclass(frozen=True)
class ExportType:
    key: str
    sql: str
    columns: tuple[str, ...]


# Her dışa aktarma sabit bir SQL'e dayanır (kullanıcı girdisi SQL'e girmez; yalnızca crawl_id parametresi)
EXPORTS: dict[str, ExportType] = {
    "status_codes": ExportType(
        "status_codes",
        "SELECT url, status_code, fetch_status, error_code, content_type, response_time_ms, redirect_url"
        " FROM pages WHERE crawl_id = ? ORDER BY status_code, url",
        ("url", "status_code", "fetch_status", "error_code", "content_type", "response_time_ms", "redirect_url"),
    ),
    "meta": ExportType(
        "meta",
        "SELECT p.url, m.title, m.title_length, m.title_count, m.meta_description, m.description_length,"
        " m.description_count, m.meta_robots, p.x_robots_tag, m.canonical, m.og_title, m.og_description, m.og_image,"
        " m.twitter_card, m.lang FROM pages p JOIN page_metadata m ON m.page_id = p.id WHERE p.crawl_id = ? ORDER BY p.url",
        ("url", "title", "title_length", "title_count", "meta_description", "description_length",
         "description_count", "meta_robots", "x_robots_tag", "canonical", "og_title", "og_description", "og_image",
         "twitter_card", "lang"),
    ),
    "headings": ExportType(
        "headings",
        "SELECT p.url, h.position, h.level, h.text FROM headings h JOIN pages p ON p.id = h.page_id"
        " WHERE p.crawl_id = ? ORDER BY p.url, h.position",
        ("url", "position", "level", "text"),
    ),
    "images": ExportType(
        "images",
        "SELECT p.url, i.src, i.alt_present, i.alt, i.decorative, i.width, i.height, i.loading, i.has_srcset,"
        " i.is_internal, r.status_code, r.content_type, r.size_bytes FROM images i JOIN pages p ON p.id = i.page_id"
        " LEFT JOIN image_resources r ON r.crawl_id = i.crawl_id AND r.src_key = i.src_key"
        " WHERE i.crawl_id = ? ORDER BY p.url, i.id",
        ("page_url", "image_url", "alt_present", "alt", "decorative", "width", "height", "loading", "srcset",
         "internal", "status_code", "content_type", "size_bytes"),
    ),
    "internal_links": ExportType(
        "internal_links",
        "SELECT s.url, l.target_url, t.status_code, l.anchor_text, l.rel, l.nofollow, l.render_only"
        " FROM links l JOIN pages s ON s.id = l.source_page_id"
        " LEFT JOIN pages t ON t.crawl_id = l.crawl_id AND t.url_key = l.target_key"
        " WHERE l.crawl_id = ? AND l.is_internal = 1 ORDER BY s.url, l.position",
        ("source_url", "target_url", "target_status", "anchor_text", "rel", "nofollow", "render_only"),
    ),
    "external_links": ExportType(
        "external_links",
        "SELECT s.url, l.target_url, l.anchor_text, l.rel, l.nofollow FROM links l JOIN pages s ON s.id = l.source_page_id"
        " WHERE l.crawl_id = ? AND l.is_internal = 0 ORDER BY s.url, l.position",
        ("source_url", "target_url", "anchor_text", "rel", "nofollow"),
    ),
    "issues": ExportType(
        "issues",
        "SELECT code, category, severity, base_severity, url, evidence, signals, detected_at FROM issues"
        " WHERE crawl_id = ? ORDER BY severity_rank, priority_score DESC, code, url",
        ("code", "category", "severity", "base_severity", "url", "evidence", "signals", "detected_at"),
    ),
    "redirects": ExportType(
        "redirects",
        "SELECT p.url, r.hop, r.from_url, r.to_url, r.status_code, r.redirect_type FROM redirects r"
        " JOIN pages p ON p.id = r.page_id WHERE r.crawl_id = ? ORDER BY p.url, r.hop",
        ("start_url", "hop", "from_url", "to_url", "status_code", "redirect_type"),
    ),
    "indexability": ExportType(
        "indexability",
        "SELECT p.url, p.status_code, p.crawlable, p.indexability, p.indexability_reason, m.meta_robots,"
        " p.x_robots_tag, m.canonical, p.in_sitemap FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id"
        " WHERE p.crawl_id = ? ORDER BY p.indexability, p.url",
        ("url", "status_code", "crawlable_robots", "indexability", "reason", "meta_robots", "x_robots_tag",
         "canonical", "in_sitemap"),
    ),
}

PAGE_COLUMNS: tuple[str, ...] = (
    "url", "status_code", "fetch_status", "content_type", "indexability", "indexability_reason", "title",
    "title_length", "meta_description", "description_length", "h1", "h1_count", "canonical", "word_count",
    "inlinks", "outlinks_internal", "outlinks_external", "crawl_depth", "response_time_ms", "issues_count",
    "in_sitemap", "rendered", "redirect_url",
)
EXPORT_KEYS: tuple[str, ...] = ("pages", *EXPORTS)


def export_rows(conn: sqlite3.Connection, crawl_id: int, key: str) -> tuple[list[str], Iterator[tuple[Any, ...]]]:
    if key == "pages":
        rows = iter_pages(conn, crawl_id, PageQuery(sort="url"))
        return list(PAGE_COLUMNS), (tuple(r.get(c) for c in PAGE_COLUMNS) for r in rows)
    export = EXPORTS[key]
    cursor = conn.execute(export.sql, (crawl_id,))
    return list(export.columns), (tuple(r) for r in cursor)


def export_selected_pages(conn: sqlite3.Connection, crawl_id: int, ids: list[int]) -> Iterator[str]:
    rows = iter_pages(conn, crawl_id, PageQuery(ids=ids, sort="url"))
    return rows_to_csv(list(PAGE_COLUMNS), (tuple(r.get(c) for c in PAGE_COLUMNS) for r in rows))


def safe_filename(*parts: str, ext: str) -> str:
    """Dosya adı: yalnızca [a-z0-9-_], uzunluk sınırlı (yol enjeksiyonu yok)."""
    import unicodedata

    cleaned: list[str] = []
    for part in parts:
        text = unicodedata.normalize("NFKD", str(part)).encode("ascii", "ignore").decode()
        text = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-").lower()
        if text:
            cleaned.append(text[:60])
    return ("_".join(cleaned) or "export") + "." + ext
