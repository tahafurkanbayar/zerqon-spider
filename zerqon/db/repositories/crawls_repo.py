"""crawl_jobs tablosu."""

from __future__ import annotations

import sqlite3
from typing import Any

from zerqon.db.connection import transaction, utcnow_iso
from zerqon.db.repositories import settings_repo
from zerqon.schemas import CrawlSettingsModel

ACTIVE_STATUSES: tuple[str, ...] = ("queued", "running", "stopping")
FINISHED_STATUSES: tuple[str, ...] = ("completed", "cancelled", "failed", "interrupted")


def create_job(
    conn: sqlite3.Connection, project_id: int, start_url: str, settings: CrawlSettingsModel
) -> int:
    """Projenin ayarlarının anlık kopyasıyla yeni tarama işi oluşturur (eski taramalar korunur)."""
    now = utcnow_iso()
    with transaction(conn):
        settings_id = settings_repo.insert_settings(conn, settings)
        cur = conn.execute(
            """
            INSERT INTO crawl_jobs(project_id, settings_id, start_url, status, permission_confirmed,
                                   permission_confirmed_at, created_at)
            VALUES (?, ?, ?, 'queued', 1, ?, ?)
            """,
            (project_id, settings_id, start_url, now, now),
        )
    return int(cur.lastrowid or 0)


def get_job(conn: sqlite3.Connection, crawl_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT j.*, p.name AS project_name FROM crawl_jobs j JOIN projects p ON p.id = j.project_id
        WHERE j.id = ?
        """,
        (crawl_id,),
    ).fetchone()
    return dict(row) if row else None


def list_jobs(conn: sqlite3.Connection, project_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT j.*, s.health_score, s.score_confidence, s.pages_total, s.indexable, s.non_indexable,
               s.issues_critical, s.issues_high, s.issues_medium, s.issues_low, s.issues_info,
               cs.max_urls, cs.render_mode
        FROM crawl_jobs j
        LEFT JOIN crawl_snapshots s ON s.crawl_id = j.id
        JOIN crawl_settings cs ON cs.id = j.settings_id
        WHERE j.project_id = ? ORDER BY j.id DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def set_status(
    conn: sqlite3.Connection,
    crawl_id: int,
    status: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    now = utcnow_iso()
    if status == "running":
        conn.execute(
            "UPDATE crawl_jobs SET status = ?, started_at = COALESCE(started_at, ?), heartbeat_at = ?,"
            " finished_at = NULL, error_code = NULL, error_message = NULL WHERE id = ?",
            (status, now, now, crawl_id),
        )
    elif status in FINISHED_STATUSES:
        conn.execute(
            "UPDATE crawl_jobs SET status = ?, finished_at = ?, error_code = COALESCE(?, error_code),"
            " error_message = COALESCE(?, error_message) WHERE id = ?",
            (status, now, error_code, error_message, crawl_id),
        )
    else:
        conn.execute("UPDATE crawl_jobs SET status = ? WHERE id = ?", (status, crawl_id))


def update_progress(conn: sqlite3.Connection, crawl_id: int, progress: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE crawl_jobs SET urls_crawled = :urls_crawled, urls_failed = :urls_failed,
               urls_queued = :urls_queued, urls_discovered = :urls_discovered,
               limit_reached = :limit_reached, last_url = :last_url, heartbeat_at = :now
        WHERE id = :id
        """,
        {**progress, "now": utcnow_iso(), "id": crawl_id},
    )


def set_robots_info(conn: sqlite3.Connection, crawl_id: int, status: str, url: str) -> None:
    conn.execute("UPDATE crawl_jobs SET robots_status = ?, robots_url = ? WHERE id = ?", (status, url, crawl_id))


def mark_running_as_interrupted(conn: sqlite3.Connection) -> int:
    """Uygulama açılışında: önceki oturumdan 'aktif' kalan taramalar yarım kalmıştır."""
    cur = conn.execute(
        "UPDATE crawl_jobs SET status = 'interrupted', finished_at = ?, error_code = 'app_shutdown'"
        " WHERE status IN ('queued', 'running', 'stopping')",
        (utcnow_iso(),),
    )
    return cur.rowcount


def increment_resume(conn: sqlite3.Connection, crawl_id: int) -> None:
    conn.execute("UPDATE crawl_jobs SET resume_count = resume_count + 1 WHERE id = ?", (crawl_id,))


def previous_completed(conn: sqlite3.Connection, crawl_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT j.* FROM crawl_jobs j
        WHERE j.project_id = (SELECT project_id FROM crawl_jobs WHERE id = :id)
          AND j.id < :id AND j.id IN (SELECT crawl_id FROM crawl_snapshots)
        ORDER BY j.id DESC LIMIT 1
        """,
        {"id": crawl_id},
    ).fetchone()
    return dict(row) if row else None


def get_snapshot(conn: sqlite3.Connection, crawl_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM crawl_snapshots WHERE crawl_id = ?", (crawl_id,)).fetchone()
    return dict(row) if row else None


def delete_job(conn: sqlite3.Connection, crawl_id: int) -> None:
    with transaction(conn):
        row = conn.execute("SELECT settings_id FROM crawl_jobs WHERE id = ?", (crawl_id,)).fetchone()
        conn.execute("DELETE FROM crawl_jobs WHERE id = ?", (crawl_id,))
        if row:
            conn.execute("DELETE FROM crawl_settings WHERE id = ?", (row[0],))
