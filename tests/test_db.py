from __future__ import annotations

import sqlite3

import pytest

from zerqon.db.migrator import current_version, latest_version, migrate
from zerqon.db.repositories import crawls_repo, projects_repo, settings_repo
from zerqon.schemas import CrawlSettingsModel, ProjectCreate


def test_migrations_applied_and_idempotent(conn: sqlite3.Connection) -> None:
    assert current_version(conn) == latest_version()
    assert migrate(conn) == []  # ikinci çalıştırma hiçbir şey uygulamaz


def test_wal_and_foreign_keys(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_project_crud_and_settings_roundtrip(conn: sqlite3.Connection) -> None:
    settings = CrawlSettingsModel(max_urls=42, include_subdomains=True, exclude_patterns="/admin/\n\\?sort=")
    pid = projects_repo.create_project(conn, ProjectCreate(name="Örnek Şirket", start_url="example.com"), settings)
    project = projects_repo.get_project(conn, pid)
    assert project is not None
    assert project["name"] == "Örnek Şirket"
    assert project["start_url"] == "https://example.com/"
    loaded = settings_repo.get_settings(conn, project["settings_id"])
    assert loaded.max_urls == 42
    assert loaded.include_subdomains is True
    assert loaded.exclude_patterns == "/admin/\n\\?sort="

    projects_repo.delete_project(conn, pid)
    assert projects_repo.get_project(conn, pid) is None
    assert conn.execute("SELECT COUNT(*) FROM crawl_settings").fetchone()[0] == 0


def test_crawl_job_requires_permission_and_snapshots_settings(conn: sqlite3.Connection) -> None:
    pid = projects_repo.create_project(conn, ProjectCreate(name="A", start_url="https://a.example/"))
    job_id = crawls_repo.create_job(conn, pid, "https://a.example/", CrawlSettingsModel(max_urls=7))
    job = crawls_repo.get_job(conn, job_id)
    assert job is not None and job["permission_confirmed"] == 1 and job["status"] == "queued"
    # Proje ayarı değişse bile taramanın kendi kopyası korunur
    project = projects_repo.get_project(conn, pid)
    assert project is not None
    settings_repo.update_settings(conn, project["settings_id"], CrawlSettingsModel(max_urls=999))
    assert settings_repo.get_settings(conn, job["settings_id"]).max_urls == 7

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO crawl_jobs(project_id, settings_id, start_url, permission_confirmed,"
            " permission_confirmed_at, created_at) VALUES (?, ?, 'x', 0, 'now', 'now')",
            (pid, job["settings_id"]),
        )


def test_running_jobs_marked_interrupted(conn: sqlite3.Connection) -> None:
    pid = projects_repo.create_project(conn, ProjectCreate(name="B", start_url="https://b.example/"))
    job_id = crawls_repo.create_job(conn, pid, "https://b.example/", CrawlSettingsModel())
    crawls_repo.set_status(conn, job_id, "running")
    assert crawls_repo.mark_running_as_interrupted(conn) == 1
    job = crawls_repo.get_job(conn, job_id)
    assert job is not None and job["status"] == "interrupted" and job["error_code"] == "app_shutdown"


def test_sql_injection_is_inert(conn: sqlite3.Connection) -> None:
    evil = "x'); DROP TABLE projects; --"
    pid = projects_repo.create_project(conn, ProjectCreate(name=evil, start_url="https://c.example/"))
    project = projects_repo.get_project(conn, pid)
    assert project is not None and project["name"] == evil
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
