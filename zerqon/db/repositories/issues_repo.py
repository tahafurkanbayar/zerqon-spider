"""Sorun özetleri ve sorun listeleri."""

from __future__ import annotations

import sqlite3
from typing import Any


def summary(
    conn: sqlite3.Connection, crawl_id: int, *, severity: str = "", category: str = ""
) -> list[dict[str, Any]]:
    """Koda göre gruplanmış sorunlar: en ciddi seviye, etkilenen URL sayısı, kayıt sayısı."""
    clauses = ["crawl_id = ?"]
    args: list[Any] = [crawl_id]
    if severity:
        clauses.append("severity = ?")
        args.append(severity)
    if category:
        clauses.append("category = ?")
        args.append(category)
    rows = conn.execute(
        f"""
        SELECT code, category, MIN(severity_rank) AS rank, COUNT(*) AS instances,
               COUNT(DISTINCT COALESCE(url_key, id)) AS urls,
               SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS n_critical,
               SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) AS n_high,
               SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END) AS n_medium,
               SUM(CASE WHEN severity = 'low' THEN 1 ELSE 0 END) AS n_low,
               SUM(CASE WHEN severity = 'info' THEN 1 ELSE 0 END) AS n_info,
               MAX(priority_score) AS top_priority
        FROM issues WHERE {' AND '.join(clauses)}
        GROUP BY code ORDER BY rank, top_priority DESC, instances DESC
        """,  # noqa: S608 - sabit yan tümceler
        args,
    ).fetchall()
    ranks = {1: "critical", 2: "high", 3: "medium", 4: "low", 5: "info"}
    return [dict(r) | {"severity": ranks[r["rank"]]} for r in rows]


def by_code(
    conn: sqlite3.Connection, crawl_id: int, code: str, *, page: int = 1, per_page: int = 50
) -> tuple[list[dict[str, Any]], int]:
    total = conn.execute("SELECT COUNT(*) FROM issues WHERE crawl_id = ? AND code = ?", (crawl_id, code)).fetchone()[0]
    rows = conn.execute(
        """
        SELECT i.id, i.page_id, i.url, i.severity, i.evidence, i.signals, i.detected_at, p.status_code, p.inlinks
        FROM issues i LEFT JOIN pages p ON p.id = i.page_id
        WHERE i.crawl_id = ? AND i.code = ?
        ORDER BY i.severity_rank, i.priority_score DESC, i.url LIMIT ? OFFSET ?
        """,
        (crawl_id, code, per_page, (max(1, page) - 1) * per_page),
    ).fetchall()
    return [dict(r) for r in rows], int(total)


def counts_by_severity(conn: sqlite3.Connection, crawl_id: int) -> dict[str, int]:
    rows = conn.execute("SELECT severity, COUNT(*) AS n FROM issues WHERE crawl_id = ? GROUP BY severity", (crawl_id,))
    data = {s: 0 for s in ("critical", "high", "medium", "low", "info")}
    data.update({r["severity"]: r["n"] for r in rows})
    return data


def counts_by_category(conn: sqlite3.Connection, crawl_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT category, COUNT(*) AS n, MIN(severity_rank) AS rank FROM issues WHERE crawl_id = ?"
        " AND severity <> 'info' GROUP BY category ORDER BY n DESC", (crawl_id,))]


def recent(conn: sqlite3.Connection, crawl_id: int, limit: int = 8) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT code, severity, url, page_id FROM issues WHERE crawl_id = ? ORDER BY id DESC LIMIT ?",
        (crawl_id, limit))]
