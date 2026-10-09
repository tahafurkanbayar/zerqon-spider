"""projects tablosu."""

from __future__ import annotations

import sqlite3
from typing import Any

from zerqon.db.connection import transaction, utcnow_iso
from zerqon.db.repositories import settings_repo
from zerqon.schemas import CrawlSettingsModel, ProjectCreate


def create_project(
    conn: sqlite3.Connection, data: ProjectCreate, settings: CrawlSettingsModel | None = None
) -> int:
    now = utcnow_iso()
    with transaction(conn):
        settings_id = settings_repo.insert_settings(conn, settings or CrawlSettingsModel())
        cur = conn.execute(
            "INSERT INTO projects(name, start_url, settings_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (data.name, data.start_url, settings_id, now, now),
        )
    return int(cur.lastrowid or 0)


def update_project(conn: sqlite3.Connection, project_id: int, data: ProjectCreate) -> None:
    conn.execute(
        "UPDATE projects SET name = ?, start_url = ?, updated_at = ? WHERE id = ?",
        (data.name, data.start_url, utcnow_iso(), project_id),
    )


def get_project(conn: sqlite3.Connection, project_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Projeleri son tamamlanmış/son taramanın özetiyle birlikte döndürür."""
    rows = conn.execute(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM crawl_jobs j WHERE j.project_id = p.id) AS crawl_count,
               lj.id AS last_crawl_id, lj.status AS last_crawl_status,
               s.health_score, s.score_confidence, s.pages_total,
               (s.issues_critical + s.issues_high + s.issues_medium + s.issues_low) AS issues_total
        FROM projects p
        LEFT JOIN crawl_jobs lj ON lj.id = (
            SELECT id FROM crawl_jobs WHERE project_id = p.id ORDER BY id DESC LIMIT 1)
        LEFT JOIN crawl_snapshots s ON s.crawl_id = lj.id
        ORDER BY p.updated_at DESC, p.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def delete_project(conn: sqlite3.Connection, project_id: int) -> None:
    with transaction(conn):
        settings_ids = [
            r[0]
            for r in conn.execute(
                "SELECT settings_id FROM projects WHERE id = ? UNION SELECT settings_id FROM crawl_jobs WHERE project_id = ?",
                (project_id, project_id),
            )
        ]
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.executemany("DELETE FROM crawl_settings WHERE id = ?", [(sid,) for sid in settings_ids])


def touch_last_crawl(conn: sqlite3.Connection, project_id: int) -> None:
    now = utcnow_iso()
    conn.execute("UPDATE projects SET last_crawl_at = ?, updated_at = ? WHERE id = ?", (now, now, project_id))
