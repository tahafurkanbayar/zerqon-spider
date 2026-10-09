"""Teknik indexlenebilirlik hesaplaması.

Üç kavram birbirinden ayrıdır:
- Taranabilirlik (crawlable): robots.txt isteğe izin veriyor mu?
- Teknik indexlenebilirlik: sayfanın kendi sinyallerine göre indekslenmeye uygun mu?
- Gerçek Google indeks durumu: Search Console olmadan BİLİNEMEZ; bu modül iddia etmez.

Öncelik sırası (ilk eşleşen neden raporlanır):
blocked_robots > blocked_security > fetch_error > redirect > client_error > server_error > no_response
> noindex > canonicalised
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from zerqon.db.connection import transaction

INDEXABLE = "indexable"
NON_INDEXABLE = "non_indexable"


def parse_directives(*values: str | None) -> set[str]:
    directives: set[str] = set()
    for value in values:
        for part in (value or "").lower().split(","):
            part = part.strip()
            if not part:
                continue
            if part == "none":
                directives.update({"noindex", "nofollow"})
            directives.add(part)
    return directives


@dataclass(frozen=True)
class IndexSignals:
    url_key: str
    fetch_status: str
    status_code: int | None
    meta_robots: str | None = None
    x_robots_tag: str | None = None
    canonical_key: str | None = None


def evaluate(signals: IndexSignals) -> tuple[str, str | None]:
    if signals.fetch_status == "blocked_robots":
        return NON_INDEXABLE, "blocked_robots"
    if signals.fetch_status == "blocked_security":
        return NON_INDEXABLE, "blocked_security"
    if signals.fetch_status != "ok" or signals.status_code is None:
        return NON_INDEXABLE, "fetch_error"
    status = signals.status_code
    if 300 <= status < 400:
        return NON_INDEXABLE, "redirect"
    if 400 <= status < 500:
        return NON_INDEXABLE, "client_error"
    if status >= 500:
        return NON_INDEXABLE, "server_error"
    if not 200 <= status < 300:
        return NON_INDEXABLE, "no_response"
    if "noindex" in parse_directives(signals.meta_robots, signals.x_robots_tag):
        return NON_INDEXABLE, "noindex"
    if signals.canonical_key and signals.canonical_key != signals.url_key:
        return NON_INDEXABLE, "canonicalised"
    return INDEXABLE, None


def apply_indexability(conn: sqlite3.Connection, crawl_id: int) -> None:
    rows = conn.execute(
        """
        SELECT p.id, p.url_key, p.fetch_status, p.status_code, p.x_robots_tag, m.meta_robots, m.canonical_key
        FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id WHERE p.crawl_id = ?
        """,
        (crawl_id,),
    ).fetchall()
    updates: list[tuple[str, str | None, int]] = []
    for row in rows:
        state, reason = evaluate(
            IndexSignals(
                url_key=row["url_key"],
                fetch_status=row["fetch_status"],
                status_code=row["status_code"],
                meta_robots=row["meta_robots"],
                x_robots_tag=row["x_robots_tag"],
                canonical_key=row["canonical_key"],
            )
        )
        updates.append((state, reason, row["id"]))
    with transaction(conn):
        conn.executemany("UPDATE pages SET indexability = ?, indexability_reason = ? WHERE id = ?", updates)
