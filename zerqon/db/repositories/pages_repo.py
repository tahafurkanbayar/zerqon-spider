"""URL tablosu ve URL detayı sorguları.

Filtreleme, sıralama ve sayfalama sunucu tarafında yapılır. Sıralama sütunları beyaz listedendir.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

SORT_COLUMNS: dict[str, str] = {
    "url": "p.url",
    "status": "p.status_code",
    "type": "p.content_type",
    "indexability": "p.indexability",
    "title": "m.title",
    "title_length": "m.title_length",
    "description": "m.meta_description",
    "h1": "m.h1",
    "words": "p.word_count",
    "inlinks": "p.inlinks",
    "outlinks": "p.outlinks_internal",
    "depth": "p.crawl_depth",
    "response": "p.response_time_ms",
    "issues": "p.issues_count",
    "id": "p.id",
}
STATUS_FILTERS: dict[str, str] = {
    "2xx": "p.status_code BETWEEN 200 AND 299",
    "3xx": "p.status_code BETWEEN 300 AND 399",
    "4xx": "p.status_code BETWEEN 400 AND 499",
    "5xx": "p.status_code >= 500",
    "error": "p.fetch_status IN ('error', 'blocked_security')",
    "blocked": "p.fetch_status = 'blocked_robots'",
}
TYPE_FILTERS: dict[str, str] = {
    "html": "p.is_html = 1",
    "other": "p.is_html = 0 AND p.fetch_status = 'ok' AND (p.status_code < 300 OR p.status_code >= 400)",
}
PER_PAGE_OPTIONS = (25, 50, 100, 250)


@dataclass
class PageQuery:
    q: str = ""
    status: str = ""
    indexability: str = ""
    content: str = ""
    issue: str = ""
    severity: str = ""
    sitemap: str = ""
    sort: str = "id"
    dir: str = "asc"
    page: int = 1
    per_page: int = 50
    ids: list[int] = field(default_factory=list)

    def normalized(self) -> PageQuery:
        self.sort = self.sort if self.sort in SORT_COLUMNS else "id"
        self.dir = "desc" if self.dir == "desc" else "asc"
        self.per_page = self.per_page if self.per_page in PER_PAGE_OPTIONS else 50
        self.page = max(1, self.page)
        self.q = self.q.strip()[:300]
        return self

    def params(self) -> dict[str, Any]:
        """Bağlantılarda taşınacak (boş olmayan) filtre parametreleri."""
        data = {
            "q": self.q, "status": self.status, "indexability": self.indexability, "content": self.content,
            "issue": self.issue, "severity": self.severity, "sitemap": self.sitemap,
            "sort": self.sort, "dir": self.dir, "per_page": self.per_page,
        }
        return {k: v for k, v in data.items() if v not in ("", None)}


def _where(crawl_id: int, query: PageQuery) -> tuple[str, list[Any]]:
    clauses = ["p.crawl_id = ?"]
    args: list[Any] = [crawl_id]
    if query.q:
        like = f"%{query.q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        clauses.append("(p.url LIKE ? ESCAPE '\\' OR m.title LIKE ? ESCAPE '\\' OR m.h1 LIKE ? ESCAPE '\\')")
        args += [like, like, like]
    if query.status in STATUS_FILTERS:
        clauses.append(STATUS_FILTERS[query.status])
    if query.indexability in ("indexable", "non_indexable"):
        clauses.append("p.indexability = ?")
        args.append(query.indexability)
    if query.content in TYPE_FILTERS:
        clauses.append(TYPE_FILTERS[query.content])
    if query.sitemap == "yes":
        clauses.append("p.in_sitemap = 1")
    elif query.sitemap == "no":
        clauses.append("p.in_sitemap = 0")
    if query.issue or query.severity:
        sub = ["i.page_id = p.id"]
        if query.issue:
            sub.append("i.code = ?")
            args.append(query.issue)
        if query.severity:
            sub.append("i.severity = ?")
            args.append(query.severity)
        clauses.append(f"EXISTS (SELECT 1 FROM issues i WHERE {' AND '.join(sub)})")
    if query.ids:
        clauses.append(f"p.id IN ({', '.join('?' for _ in query.ids)})")
        args += query.ids
    return " AND ".join(clauses), args


TABLE_SELECT = """
    SELECT p.id, p.url, p.status_code, p.fetch_status, p.content_type, p.indexability, p.indexability_reason,
           p.word_count, p.inlinks, p.outlinks_internal, p.outlinks_external, p.crawl_depth, p.response_time_ms,
           p.issues_count, p.in_sitemap, p.rendered, p.redirect_url, p.error_code,
           m.title, m.title_length, m.meta_description, m.description_length, m.h1, m.h1_count, m.canonical
    FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id
"""


def query_pages(conn: sqlite3.Connection, crawl_id: int, query: PageQuery) -> tuple[list[dict[str, Any]], int]:
    query.normalized()
    where, args = _where(crawl_id, query)
    total = conn.execute(
        f"SELECT COUNT(*) FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id WHERE {where}", args  # noqa: S608
    ).fetchone()[0]
    order = f"{SORT_COLUMNS[query.sort]} {'DESC' if query.dir == 'desc' else 'ASC'} NULLS LAST, p.id ASC"
    rows = conn.execute(
        f"{TABLE_SELECT} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",  # noqa: S608 - beyaz liste
        [*args, query.per_page, (query.page - 1) * query.per_page],
    ).fetchall()
    return [dict(r) for r in rows], int(total)


def iter_pages(conn: sqlite3.Connection, crawl_id: int, query: PageQuery) -> list[dict[str, Any]]:
    """Dışa aktarma için filtreye uyan tüm satırlar (sayfalama yok)."""
    query.normalized()
    where, args = _where(crawl_id, query)
    order = f"{SORT_COLUMNS[query.sort]} {'DESC' if query.dir == 'desc' else 'ASC'} NULLS LAST, p.id ASC"
    rows = conn.execute(f"{TABLE_SELECT} WHERE {where} ORDER BY {order}", args).fetchall()  # noqa: S608
    return [dict(r) for r in rows]


def get_page(conn: sqlite3.Connection, crawl_id: int, page_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT p.*, m.* FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id WHERE p.crawl_id = ? AND p.id = ?",
        (crawl_id, page_id),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["id"] = page_id  # m.page_id ile çakışmasın
    return data


def page_details(conn: sqlite3.Connection, crawl_id: int, page: dict[str, Any]) -> dict[str, Any]:
    pid = page["id"]
    return {
        "headings": [dict(r) for r in conn.execute(
            "SELECT level, text FROM headings WHERE page_id = ? ORDER BY position", (pid,))],
        "outlinks": [dict(r) for r in conn.execute(
            """
            SELECT l.target_url, l.anchor_text, l.rel, l.nofollow, l.is_internal, l.render_only,
                   t.id AS target_id, t.status_code AS target_status
            FROM links l LEFT JOIN pages t ON t.crawl_id = l.crawl_id AND t.url_key = l.target_key
            WHERE l.source_page_id = ? ORDER BY l.position LIMIT 1000
            """, (pid,))],
        "inlinks": [dict(r) for r in conn.execute(
            """
            SELECT s.id AS source_id, s.url AS source_url, l.anchor_text, l.nofollow, l.render_only
            FROM links l JOIN pages s ON s.id = l.source_page_id
            WHERE l.crawl_id = ? AND l.target_key = ? ORDER BY s.url LIMIT 1000
            """, (crawl_id, page["url_key"]))],
        "images": [dict(r) for r in conn.execute(
            """
            SELECT i.src, i.alt, i.alt_present, i.width, i.height, i.loading, i.has_srcset, i.decorative, i.is_internal,
                   r.status_code, r.size_bytes, r.content_type
            FROM images i LEFT JOIN image_resources r ON r.crawl_id = i.crawl_id AND r.src_key = i.src_key
            WHERE i.page_id = ? ORDER BY i.id
            """, (pid,))],
        "structured": [dict(r) for r in conn.execute(
            "SELECT format, schema_type, valid, error, missing_fields FROM structured_data WHERE page_id = ?", (pid,))],
        "hreflang": [dict(r) for r in conn.execute(
            """
            SELECT h.lang, h.href, t.id AS target_id, t.status_code AS target_status
            FROM hreflang h LEFT JOIN pages t ON t.crawl_id = ? AND t.url_key = h.href_key
            WHERE h.page_id = ?
            """, (crawl_id, pid))],
        "redirects": [dict(r) for r in conn.execute(
            "SELECT hop, from_url, to_url, status_code, redirect_type FROM redirects WHERE page_id = ? ORDER BY hop",
            (pid,))],
        "issues": [dict(r) for r in conn.execute(
            "SELECT code, category, severity, base_severity, evidence, signals FROM issues WHERE page_id = ?"
            " ORDER BY severity_rank, code", (pid,))],
    }


def status_distribution(conn: sqlite3.Connection, crawl_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT status_code, fetch_status, COUNT(*) AS n FROM pages WHERE crawl_id = ?"
        " GROUP BY status_code, fetch_status ORDER BY n DESC",
        (crawl_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def events(conn: sqlite3.Connection, crawl_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT created_at, level, code, detail FROM crawl_events WHERE crawl_id = ? ORDER BY id", (crawl_id,))]


def recent_pages(conn: sqlite3.Connection, crawl_id: int, limit: int = 8) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT id, url, status_code, fetch_status, response_time_ms FROM pages WHERE crawl_id = ?"
        " ORDER BY id DESC LIMIT ?", (crawl_id, limit))]
