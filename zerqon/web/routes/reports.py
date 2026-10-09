"""Raporlar (CSV/HTML), tarama karşılaştırması, yedekleme/geri yükleme."""

from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from zerqon.config import Settings
from zerqon.crawler.manager import CrawlManager
from zerqon.db.connection import Database
from zerqon.db.repositories import crawls_repo
from zerqon.i18n import SUPPORTED_LANGUAGES
from zerqon.reports.backup import BackupError, create_backup, list_backups, restore_backup
from zerqon.reports.compare import CompareError, compare_crawls
from zerqon.reports.csv_export import EXPORT_KEYS
from zerqon.reports.html_report import save_report
from zerqon.web.deps import get_app_settings, get_conn, get_db, redirect, require
from zerqon.web.routes.crawls import _crawl_context, get_manager
from zerqon.web.templating import render

router = APIRouter()

_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.zip$")
MAX_UPLOAD_BYTES = 4 * 1024**3
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"


def project_reports(conn: sqlite3.Connection, project_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM reports WHERE project_id = ? ORDER BY id DESC", (project_id,))]


# ----------------------------------------------------------------------------- raporlar
@router.get("/crawls/{crawl_id}/reports", response_class=HTMLResponse)
def reports_tab(crawl_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    ctx = _crawl_context(conn, crawl_id)
    ctx.update(
        tab="reports",
        export_keys=EXPORT_KEYS,
        reports=[r for r in project_reports(conn, ctx["project"]["id"]) if r["crawl_id"] == crawl_id],
        msg=request.query_params.get("msg", ""),
        is_active=ctx["job"]["status"] in crawls_repo.ACTIVE_STATUSES,
    )
    return render(request, "crawls/reports.html", ctx)


@router.post("/crawls/{crawl_id}/reports/html", response_model=None)
def generate_html_report(
    crawl_id: int,
    request: Request,
    language: str = Form("tr"),
    conn: sqlite3.Connection = Depends(get_conn),
    app_settings: Settings = Depends(get_app_settings),
) -> Response:
    job = require(crawls_repo.get_job(conn, crawl_id))
    if job["status"] in crawls_repo.ACTIVE_STATUSES:
        return redirect(f"/crawls/{crawl_id}/reports?msg=flash.report_busy", request)
    language = language if language in SUPPORTED_LANGUAGES else "tr"
    save_report(conn, crawl_id, app_settings.reports_dir, language)
    return redirect(f"/crawls/{crawl_id}/reports?msg=flash.report_created", request)


def _report_path(conn: sqlite3.Connection, report_id: int, app_settings: Settings) -> tuple[dict[str, Any], Path]:
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404)
    base = app_settings.reports_dir.resolve()
    path = (base / row["filename"]).resolve()
    if path.parent != base or not path.is_file():
        raise HTTPException(status_code=404)
    return dict(row), path


@router.get("/reports/{report_id}", response_model=None)
def view_report(
    report_id: int,
    download: int = 0,
    conn: sqlite3.Connection = Depends(get_conn),
    app_settings: Settings = Depends(get_app_settings),
) -> Response:
    row, path = _report_path(conn, report_id, app_settings)
    headers = {"Content-Security-Policy": REPORT_CSP}
    if download:
        return FileResponse(path, media_type="text/html; charset=utf-8", filename=row["filename"], headers=headers)
    return FileResponse(path, media_type="text/html; charset=utf-8", headers=headers)


@router.post("/reports/{report_id}/delete", response_model=None)
def delete_report(
    report_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    app_settings: Settings = Depends(get_app_settings),
) -> Response:
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404)
    try:
        _, path = _report_path(conn, report_id, app_settings)
        path.unlink(missing_ok=True)
    except HTTPException:
        pass  # dosya zaten yok; kaydı yine de sil
    conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    target = f"/crawls/{row['crawl_id']}/reports" if row["crawl_id"] else f"/projects/{row['project_id']}"
    return redirect(f"{target}?msg=flash.report_deleted", request)


# ----------------------------------------------------------------------------- karşılaştırma
@router.get("/compare", response_class=HTMLResponse)
def compare(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    qp = request.query_params
    ids: list[int] = []
    for raw in [qp.get("a"), qp.get("b"), *qp.getlist("crawl")]:
        if raw and raw.isdigit() and int(raw) not in ids:
            ids.append(int(raw))
    if len(ids) != 2:
        return render(request, "compare.html", {"nav": "projects", "error": "pick_two"}, status_code=400)
    try:
        result = compare_crawls(conn, ids[0], ids[1])
    except CompareError as exc:
        return render(request, "compare.html", {"nav": "projects", "error": exc.code}, status_code=400)
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (result.a["project_id"],)).fetchone()
    return render(request, "compare.html", {"nav": "projects", "c": result, "project": dict(project), "error": None})


# ----------------------------------------------------------------------------- yedekleme
@router.post("/settings/backup", response_model=None)
def make_backup(
    request: Request,
    db: Database = Depends(get_db),
    app_settings: Settings = Depends(get_app_settings),
) -> Response:
    create_backup(db, app_settings.backups_dir)
    return redirect("/settings?msg=flash.backup_created", request)


@router.get("/settings/backups/{name}", response_model=None)
def download_backup(name: str, app_settings: Settings = Depends(get_app_settings)) -> Response:
    if not _BACKUP_NAME_RE.match(name):
        raise HTTPException(status_code=404)
    base = app_settings.backups_dir.resolve()
    path = (base / name).resolve()
    if path.parent != base or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="application/zip", filename=name)


@router.post("/settings/restore", response_model=None)
async def restore(
    request: Request,
    file: UploadFile,
    db: Database = Depends(get_db),
    app_settings: Settings = Depends(get_app_settings),
    manager: CrawlManager = Depends(get_manager),
) -> Response:
    if manager.active_ids():
        return redirect("/settings?msg=flash.restore_busy", request)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "upload.zip"
        written = 0
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    return redirect("/settings?msg=flash.restore_failed", request)
                out.write(chunk)
        try:
            restore_backup(db, target, app_settings.backups_dir)
        except BackupError:
            return redirect("/settings?msg=flash.restore_failed", request)
    return redirect("/settings?msg=flash.restore_done", request)


def backups_context(app_settings: Settings) -> list[dict[str, Any]]:
    return list_backups(app_settings.backups_dir)

