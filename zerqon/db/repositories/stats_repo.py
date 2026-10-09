"""Dashboard için toplu istatistikler (her projenin en son taramasının snapshot'ı üzerinden)."""

from __future__ import annotations

import sqlite3
from typing import Any

_SNAPSHOT_SUM_FIELDS: tuple[str, ...] = (
    "pages_total",
    "pages_html",
    "pages_failed",
    "status_2xx",
    "status_3xx",
    "status_4xx",
    "status_5xx",
    "status_other",
    "blocked_robots",
    "indexable",
    "non_indexable",
    "issues_critical",
    "issues_high",
    "issues_medium",
    "issues_low",
    "issues_info",
)

_LATEST_SNAPSHOT_CTE = """
WITH latest AS (
    SELECT j.project_id, MAX(j.id) AS crawl_id
    FROM crawl_jobs j JOIN crawl_snapshots s ON s.crawl_id = j.id
    WHERE (:project_id IS NULL OR j.project_id = :project_id)
    GROUP BY j.project_id
)
"""


def dashboard_totals(conn: sqlite3.Connection, project_id: int | None = None) -> dict[str, Any]:
    sums = ", ".join(f"COALESCE(SUM(s.{f}), 0) AS {f}" for f in _SNAPSHOT_SUM_FIELDS)
    row = conn.execute(
        _LATEST_SNAPSHOT_CTE
        + f"""
        SELECT {sums},
               AVG(s.avg_response_ms) AS avg_response_ms,
               AVG(s.health_score) AS health_score,
               COUNT(s.crawl_id) AS crawled_projects
        FROM latest l JOIN crawl_snapshots s ON s.crawl_id = l.crawl_id
        """,  # noqa: S608 - sabit sütun listesi
        {"project_id": project_id},
    ).fetchone()
    totals = dict(row)
    if project_id is None:
        totals["projects"] = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    else:
        totals["projects"] = 1
    totals["running"] = conn.execute(
        "SELECT COUNT(*) FROM crawl_jobs WHERE status IN ('queued', 'running', 'stopping')"
        " AND (:p IS NULL OR project_id = :p)",
        {"p": project_id},
    ).fetchone()[0]
    return totals


def recent_crawls(conn: sqlite3.Connection, limit: int = 8, project_id: int | None = None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT j.*, p.name AS project_name, s.health_score, s.pages_total,
               (s.issues_critical + s.issues_high) AS issues_severe
        FROM crawl_jobs j
        JOIN projects p ON p.id = j.project_id
        LEFT JOIN crawl_snapshots s ON s.crawl_id = j.id
        WHERE (:p IS NULL OR j.project_id = :p)
        ORDER BY j.id DESC LIMIT :limit
        """,
        {"p": project_id, "limit": limit},
    ).fetchall()
    return [dict(r) for r in rows]


def active_crawls(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT j.*, p.name AS project_name FROM crawl_jobs j JOIN projects p ON p.id = j.project_id
        WHERE j.status IN ('queued', 'running', 'stopping') ORDER BY j.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def project_trends(conn: sqlite3.Connection, project_id: int | None = None) -> list[dict[str, Any]]:
    """Her proje için son iki snapshot arasındaki fark."""
    rows = conn.execute(
        """
        SELECT p.id AS project_id, p.name,
               cur.crawl_id AS cur_id, prev.crawl_id AS prev_id,
               cur.health_score AS cur_score, prev.health_score AS prev_score,
               cur.pages_total AS cur_pages, prev.pages_total AS prev_pages,
               (cur.issues_critical + cur.issues_high + cur.issues_medium + cur.issues_low) AS cur_issues,
               (prev.issues_critical + prev.issues_high + prev.issues_medium + prev.issues_low) AS prev_issues,
               cur.indexable AS cur_indexable, prev.indexable AS prev_indexable
        FROM projects p
        JOIN crawl_snapshots cur ON cur.crawl_id = (
            SELECT s.crawl_id FROM crawl_snapshots s JOIN crawl_jobs j ON j.id = s.crawl_id
            WHERE j.project_id = p.id ORDER BY s.crawl_id DESC LIMIT 1)
        LEFT JOIN crawl_snapshots prev ON prev.crawl_id = (
            SELECT s.crawl_id FROM crawl_snapshots s JOIN crawl_jobs j ON j.id = s.crawl_id
            WHERE j.project_id = p.id ORDER BY s.crawl_id DESC LIMIT 1 OFFSET 1)
        WHERE (:p IS NULL OR p.id = :p)
        ORDER BY p.name
        """,
        {"p": project_id},
    ).fetchall()
    return [dict(r) for r in rows]
