"""Tarama ekranları: başlatma (izin onayı), canlı ilerleme, sonuçlar, URL tablosu/detayı, sorunlar."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from zerqon.analysis.issues import REGISTRY, Category
from zerqon.crawler.manager import CrawlError, CrawlManager
from zerqon.db.repositories import crawls_repo, issues_repo, pages_repo, projects_repo, settings_repo
from zerqon.db.repositories.pages_repo import PER_PAGE_OPTIONS, PageQuery
from zerqon.reports.csv_export import EXPORT_KEYS, export_rows, export_selected_pages, rows_to_csv, safe_filename
from zerqon.web.deps import get_conn, redirect, require
from zerqon.web.templating import render

router = APIRouter()


def get_manager(request: Request) -> CrawlManager:
    return request.app.state.manager  # type: ignore[no-any-return]


def _crawl_context(conn: sqlite3.Connection, crawl_id: int) -> dict[str, Any]:
    job = require(crawls_repo.get_job(conn, crawl_id))
    project = require(projects_repo.get_project(conn, job["project_id"]))
    return {
        "job": job,
        "project": project,
        "crawl_settings": settings_repo.get_settings(conn, job["settings_id"]),
        "snapshot": crawls_repo.get_snapshot(conn, crawl_id),
        "nav": "projects",
    }


def _elapsed(job: dict[str, Any]) -> float | None:
    if not job.get("started_at"):
        return None
    start = datetime.fromisoformat(job["started_at"])
    end = datetime.fromisoformat(job["finished_at"]) if job.get("finished_at") else datetime.now(UTC)
    return max(0.0, (end - start).total_seconds())


def _progress(manager: CrawlManager, job: dict[str, Any]) -> dict[str, Any]:
    live = manager.progress(job["id"])
    if live and job["status"] in crawls_repo.ACTIVE_STATUSES:
        return live | {"live": True}
    elapsed = _elapsed(job)
    return {
        "crawled": job["urls_crawled"],
        "failed": job["urls_failed"],
        "queued": job["urls_queued"],
        "discovered": job["urls_discovered"],
        "issues": None,
        "last_url": job["last_url"] or "",
        "phase": "done",
        "status": job["status"],
        "limit_reached": bool(job["limit_reached"]),
        "elapsed": elapsed,
        "rate": round(job["urls_crawled"] / elapsed, 2) if elapsed else 0,
        "live": False,
    }


# ----------------------------------------------------------------------------- başlatma
@router.get("/projects/{project_id}/crawl", response_class=HTMLResponse)
def start_form(project_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    project = require(projects_repo.get_project(conn, project_id))
    settings = settings_repo.get_settings(conn, project["settings_id"])
    return render(
        request,
        "crawls/start.html",
        {
            "nav": "projects",
            "project": project,
            "settings": settings,
            "localhost_enabled": request.app.state.settings.allow_localhost,
            "error": request.query_params.get("error", ""),
        },
    )


@router.post("/projects/{project_id}/crawl", response_model=None)
def start_crawl(
    project_id: int,
    request: Request,
    permission_confirmed: str = Form(""),
    conn: sqlite3.Connection = Depends(get_conn),
    manager: CrawlManager = Depends(get_manager),
) -> Response:
    require(projects_repo.get_project(conn, project_id))
    try:
        crawl_id = manager.start(project_id, permission_confirmed=permission_confirmed in ("on", "true", "1"))
    except CrawlError as exc:
        return redirect(f"/projects/{project_id}/crawl?error={exc.code}", request)
    return redirect(f"/crawls/{crawl_id}", request)


# ----------------------------------------------------------------------------- genel bakış + canlı ilerleme
@router.get("/crawls/{crawl_id}", response_class=HTMLResponse)
def crawl_overview(
    crawl_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    manager: CrawlManager = Depends(get_manager),
) -> HTMLResponse:
    ctx = _crawl_context(conn, crawl_id)
    job = ctx["job"]
    ctx.update(
        tab="overview",
        progress=_progress(manager, job),
        events=pages_repo.events(conn, crawl_id),
        severity_counts=issues_repo.counts_by_severity(conn, crawl_id),
        categories=issues_repo.counts_by_category(conn, crawl_id),
        top_issues=issues_repo.summary(conn, crawl_id)[:10],
        recent_pages=pages_repo.recent_pages(conn, crawl_id),
        recent_issues=issues_repo.recent(conn, crawl_id),
        statuses=pages_repo.status_distribution(conn, crawl_id),
        is_active=job["status"] in crawls_repo.ACTIVE_STATUSES,
        resumable=job["status"] in ("interrupted", "cancelled", "failed"),
        previous=crawls_repo.previous_completed(conn, crawl_id),
        msg=request.query_params.get("msg", ""),
    )
    return render(request, "crawls/overview.html", ctx)


@router.get("/crawls/{crawl_id}/progress", response_class=HTMLResponse)
def crawl_progress(
    crawl_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    manager: CrawlManager = Depends(get_manager),
) -> HTMLResponse:
    job = require(crawls_repo.get_job(conn, crawl_id))
    if job["status"] not in crawls_repo.ACTIVE_STATUSES:
        # Tarama bitti: tam sayfa yenilensin ve sonuç görünümü gelsin
        return HTMLResponse("", headers={"HX-Refresh": "true"})
    return render(
        request,
        "crawls/_progress.html",
        {
            "job": job,
            "progress": _progress(manager, job),
            "recent_pages": pages_repo.recent_pages(conn, crawl_id),
            "recent_issues": issues_repo.recent(conn, crawl_id),
            "max_urls": settings_repo.get_settings(conn, job["settings_id"]).max_urls,
        },
    )


@router.post("/crawls/{crawl_id}/stop", response_model=None)
def stop_crawl(crawl_id: int, request: Request, manager: CrawlManager = Depends(get_manager)) -> Response:
    manager.stop(crawl_id)
    return redirect(f"/crawls/{crawl_id}?msg=flash.crawl_stopping", request)


@router.post("/crawls/{crawl_id}/resume", response_model=None)
def resume_crawl(crawl_id: int, request: Request, manager: CrawlManager = Depends(get_manager)) -> Response:
    try:
        manager.resume(crawl_id)
    except CrawlError as exc:
        return redirect(f"/crawls/{crawl_id}?msg=flash.resume_{exc.code}", request)
    return redirect(f"/crawls/{crawl_id}", request)


@router.post("/crawls/{crawl_id}/delete", response_model=None)
def delete_crawl(
    crawl_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    manager: CrawlManager = Depends(get_manager),
) -> Response:
    job = require(crawls_repo.get_job(conn, crawl_id))
    if manager.is_running(crawl_id) or job["status"] in crawls_repo.ACTIVE_STATUSES:
        return redirect(f"/crawls/{crawl_id}?msg=flash.crawl_busy", request)
    crawls_repo.delete_job(conn, crawl_id)
    return redirect(f"/projects/{job['project_id']}?msg=flash.crawl_deleted", request)


# ----------------------------------------------------------------------------- URL tablosu
def _page_query(request: Request) -> PageQuery:
    qp = request.query_params

    def to_int(name: str, default: int) -> int:
        try:
            return int(qp.get(name, default))
        except ValueError:
            return default

    return PageQuery(
        q=qp.get("q", ""),
        status=qp.get("status", ""),
        indexability=qp.get("indexability", ""),
        content=qp.get("content", ""),
        issue=qp.get("issue", "") if qp.get("issue", "") in REGISTRY else "",
        severity=qp.get("severity", "") if qp.get("severity", "") in ("critical", "high", "medium", "low", "info") else "",
        sitemap=qp.get("sitemap", ""),
        sort=qp.get("sort", "id"),
        dir=qp.get("dir", "asc"),
        page=to_int("page", 1),
        per_page=to_int("per_page", 50),
    ).normalized()


@router.get("/crawls/{crawl_id}/pages", response_class=HTMLResponse)
def crawl_pages(crawl_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    query = _page_query(request)
    rows, total = pages_repo.query_pages(conn, crawl_id, query)
    ctx: dict[str, Any] = {
        "rows": rows,
        "total": total,
        "query": query,
        "params": query.params(),
        "pages": max(1, -(-total // query.per_page)),
        "per_page_options": PER_PAGE_OPTIONS,
        "issue_codes": sorted(r["code"] for r in issues_repo.summary(conn, crawl_id)),
        "crawl_id": crawl_id,
    }
    if request.headers.get("HX-Request") == "true" and request.headers.get("HX-Target") == "pages-table":
        return render(request, "crawls/_pages_table.html", ctx)
    ctx.update(_crawl_context(conn, crawl_id), tab="pages")
    return render(request, "crawls/pages.html", ctx)


@router.post("/crawls/{crawl_id}/pages/export", response_model=None)
async def export_selected(crawl_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    require(crawls_repo.get_job(conn, crawl_id))
    form = await request.form()
    ids: list[int] = []
    for value in form.getlist("page_id"):
        try:
            ids.append(int(str(value)))
        except ValueError:
            continue
    if not ids:
        raise HTTPException(status_code=400, detail="no_selection")
    filename = safe_filename("zerqon", f"crawl-{crawl_id}", "selected-urls", ext="csv")
    return StreamingResponse(
        export_selected_pages(conn, crawl_id, ids[:10_000]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/crawls/{crawl_id}/export/{key}.csv", response_model=None)
def export_csv(crawl_id: int, key: str, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    job = require(crawls_repo.get_job(conn, crawl_id))
    if key not in EXPORT_KEYS:
        raise HTTPException(status_code=404)
    header, rows = export_rows(conn, crawl_id, key)
    filename = safe_filename("zerqon", job["project_name"], f"crawl-{crawl_id}", key, ext="csv")
    return StreamingResponse(
        rows_to_csv(header, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------------- URL detayı
@router.get("/crawls/{crawl_id}/pages/{page_id}", response_class=HTMLResponse)
def page_detail(
    crawl_id: int, page_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)
) -> HTMLResponse:
    page = require(pages_repo.get_page(conn, crawl_id, page_id))
    ctx = _crawl_context(conn, crawl_id)
    details = pages_repo.page_details(conn, crawl_id, page)
    for item in details["issues"]:
        item["signals_parsed"] = json.loads(item["signals"]) if item["signals"] else {}
    ctx.update(page=page, tab="pages", section=request.query_params.get("section", "overview"), **details)
    return render(request, "crawls/page_detail.html", ctx)


# ----------------------------------------------------------------------------- sorunlar
@router.get("/crawls/{crawl_id}/issues", response_class=HTMLResponse)
def crawl_issues(crawl_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    severity = request.query_params.get("severity", "")
    severity = severity if severity in ("critical", "high", "medium", "low", "info") else ""
    category = request.query_params.get("category", "")
    category = category if category in {c.value for c in Category} else ""
    ctx: dict[str, Any] = {
        "groups": issues_repo.summary(conn, crawl_id, severity=severity, category=category),
        "severity": severity,
        "category": category,
        "categories": [c.value for c in Category],
        "crawl_id": crawl_id,
        "severity_counts": issues_repo.counts_by_severity(conn, crawl_id),
    }
    if request.headers.get("HX-Request") == "true" and request.headers.get("HX-Target") == "issues-list":
        return render(request, "crawls/_issues_list.html", ctx)
    ctx.update(_crawl_context(conn, crawl_id), tab="issues")
    return render(request, "crawls/issues.html", ctx)


@router.get("/crawls/{crawl_id}/issues/{code}", response_class=HTMLResponse)
def issue_urls(
    crawl_id: int, code: str, request: Request, page: int = 1, conn: sqlite3.Connection = Depends(get_conn)
) -> HTMLResponse:
    if code not in REGISTRY:
        raise HTTPException(status_code=404)
    require(crawls_repo.get_job(conn, crawl_id))
    rows, total = issues_repo.by_code(conn, crawl_id, code, page=page, per_page=25)
    return render(
        request,
        "crawls/_issue_urls.html",
        {"rows": rows, "total": total, "code": code, "page": max(1, page), "pages": max(1, -(-total // 25)),
         "crawl_id": crawl_id, "definition": REGISTRY[code]},
    )
