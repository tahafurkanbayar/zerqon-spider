"""Tarama sonrası bağlantı grafiği hesaplamaları (idempotent; devam ettirme sonrası tekrar çalışabilir).

- Gelen/giden bağlantı sayıları
- Tık derinliği (başlangıç URL'sinden BFS; bağlantı + yönlendirme kenarları)
- Yönlendirme zincirleri ve döngüler (`redirects` tablosu)
- Sitemap'te bulunma işareti
"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass

from zerqon.crawler.urls import url_key
from zerqon.db.connection import transaction

MAX_CHAIN = 20


@dataclass
class ChainResult:
    hops: list[tuple[str, str, int | None, str | None]]  # (from, to, status, type)
    final_url: str | None
    final_status: int | None
    loop: bool
    final_crawled: bool


def compute_link_counts(conn: sqlite3.Connection, crawl_id: int) -> None:
    params = {"c": crawl_id}
    conn.execute(
        "UPDATE pages SET inlinks = 0, unique_inlinks = 0, outlinks_internal = 0, outlinks_external = 0"
        " WHERE crawl_id = :c",
        params,
    )
    conn.execute(
        """
        UPDATE pages SET inlinks = a.c, unique_inlinks = a.u
        FROM (SELECT target_key, COUNT(*) AS c, COUNT(DISTINCT source_page_id) AS u
              FROM links WHERE crawl_id = :c AND is_internal = 1 GROUP BY target_key) AS a
        WHERE pages.crawl_id = :c AND pages.url_key = a.target_key
        """,
        params,
    )
    conn.execute(
        """
        UPDATE pages SET outlinks_internal = a.i, outlinks_external = a.e
        FROM (SELECT source_page_id, SUM(is_internal) AS i, SUM(1 - is_internal) AS e
              FROM links WHERE crawl_id = :c GROUP BY source_page_id) AS a
        WHERE pages.id = a.source_page_id
        """,
        params,
    )


def compute_crawl_depth(conn: sqlite3.Connection, crawl_id: int) -> None:
    key_to_id: dict[str, int] = {}
    redirect_edges: dict[int, str] = {}
    start_id: int | None = None
    for row in conn.execute(
        "SELECT id, url_key, source, redirect_url FROM pages WHERE crawl_id = ?", (crawl_id,)
    ):
        key_to_id[row["url_key"]] = row["id"]
        if row["source"] == "seed":
            start_id = row["id"]
        if row["redirect_url"]:
            redirect_edges[row["id"]] = url_key(row["redirect_url"])
    conn.execute("UPDATE pages SET crawl_depth = NULL WHERE crawl_id = ?", (crawl_id,))
    if start_id is None:
        return
    adjacency: dict[int, list[int]] = {}
    for row in conn.execute(
        "SELECT source_page_id, target_key FROM links WHERE crawl_id = ? AND is_internal = 1", (crawl_id,)
    ):
        target = key_to_id.get(row[1])
        if target is not None:
            adjacency.setdefault(row[0], []).append(target)
    for source, target_key in redirect_edges.items():
        target = key_to_id.get(target_key)
        if target is not None:
            adjacency.setdefault(source, []).append(target)

    depth: dict[int, int] = {start_id: 0}
    queue: deque[int] = deque([start_id])
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, ()):
            if nxt not in depth:
                # Yönlendirme hedefi aynı tık derinliğinde sayılır
                depth[nxt] = depth[node] + (0 if redirect_edges.get(node) and key_to_id.get(redirect_edges[node]) == nxt else 1)
                queue.append(nxt)
    conn.executemany("UPDATE pages SET crawl_depth = ? WHERE id = ?", [(d, pid) for pid, d in depth.items()])


def follow_chain(start_key: str, pages: dict[str, sqlite3.Row]) -> ChainResult:
    hops: list[tuple[str, str, int | None, str | None]] = []
    visited = {start_key}
    current = pages[start_key]
    while current["redirect_url"] and len(hops) < MAX_CHAIN:
        target = current["redirect_url"]
        hops.append((current["url"], target, current["status_code"], current["redirect_type"]))
        target_key = url_key(target)
        if target_key in visited:
            return ChainResult(hops, target, None, True, True)
        visited.add(target_key)
        nxt = pages.get(target_key)
        if nxt is None:
            return ChainResult(hops, target, None, False, False)
        current = nxt
    return ChainResult(hops, current["url"], current["status_code"], False, True)


def compute_redirect_chains(conn: sqlite3.Connection, crawl_id: int) -> None:
    pages = {
        row["url_key"]: row
        for row in conn.execute(
            "SELECT id, url, url_key, status_code, redirect_url, redirect_type FROM pages WHERE crawl_id = ?",
            (crawl_id,),
        )
    }
    conn.execute("DELETE FROM redirects WHERE crawl_id = ?", (crawl_id,))
    rows: list[tuple[int, int, int, str, str, int | None, str | None]] = []
    for key, page in pages.items():
        if not page["redirect_url"]:
            continue
        chain = follow_chain(key, pages)
        for hop, (src, dst, status, rtype) in enumerate(chain.hops):
            rows.append((crawl_id, page["id"], hop, src, dst, status, rtype))
    conn.executemany(
        "INSERT INTO redirects(crawl_id, page_id, hop, from_url, to_url, status_code, redirect_type)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def compute_sitemap_flags(conn: sqlite3.Connection, crawl_id: int) -> None:
    conn.execute(
        "UPDATE pages SET in_sitemap = EXISTS (SELECT 1 FROM sitemap_urls s WHERE s.crawl_id = pages.crawl_id"
        " AND s.url_key = pages.url_key) WHERE crawl_id = ?",
        (crawl_id,),
    )


def compute_graph(conn: sqlite3.Connection, crawl_id: int) -> None:
    with transaction(conn):
        compute_link_counts(conn, crawl_id)
        compute_crawl_depth(conn, crawl_id)
        compute_redirect_chains(conn, crawl_id)
        compute_sitemap_flags(conn, crawl_id)
