"""Tarama sonu özet (crawl_snapshots) — dashboard ve karşılaştırma için hızlı erişim."""

from __future__ import annotations

import sqlite3
from typing import Any

from zerqon.db.connection import transaction, utcnow_iso


def compute_counts(conn: sqlite3.Connection, crawl_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS pages_total,
               SUM(is_html) AS pages_html,
               SUM(CASE WHEN fetch_status IN ('error', 'blocked_security') THEN 1 ELSE 0 END) AS pages_failed,
               SUM(CASE WHEN status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END) AS status_2xx,
               SUM(CASE WHEN status_code BETWEEN 300 AND 399 THEN 1 ELSE 0 END) AS status_3xx,
               SUM(CASE WHEN status_code BETWEEN 400 AND 499 THEN 1 ELSE 0 END) AS status_4xx,
               SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS status_5xx,
               SUM(CASE WHEN status_code IS NULL OR status_code < 200 THEN 1 ELSE 0 END) AS status_other,
               SUM(CASE WHEN fetch_status = 'blocked_robots' THEN 1 ELSE 0 END) AS blocked_robots,
               SUM(CASE WHEN indexability = 'indexable' THEN 1 ELSE 0 END) AS indexable,
               SUM(CASE WHEN indexability = 'non_indexable' THEN 1 ELSE 0 END) AS non_indexable,
               AVG(CASE WHEN fetch_status = 'ok' THEN response_time_ms END) AS avg_response_ms
        FROM pages WHERE crawl_id = ?
        """,
        (crawl_id,),
    ).fetchone()
    counts = {k: (row[k] or 0) for k in row.keys()}
    counts["avg_response_ms"] = row["avg_response_ms"]
    for sev in ("critical", "high", "medium", "low", "info"):
        counts[f"issues_{sev}"] = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE crawl_id = ? AND severity = ?", (crawl_id, sev)
        ).fetchone()[0]
    return counts


def save_snapshot(conn: sqlite3.Connection, crawl_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = compute_counts(conn, crawl_id)
    data.update(extra or {})
    data["crawl_id"] = crawl_id
    data["computed_at"] = utcnow_iso()
    columns = list(data)
    with transaction(conn):
        conn.execute("DELETE FROM crawl_snapshots WHERE crawl_id = ?", (crawl_id,))
        conn.execute(
            f"INSERT INTO crawl_snapshots({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",  # noqa: S608
            [data[c] for c in columns],
        )
    return data
