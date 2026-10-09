"""Ana sayfa (dashboard)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from zerqon.db.repositories import projects_repo, stats_repo
from zerqon.web.deps import get_conn
from zerqon.web.templating import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, project: int | None = None, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    projects = projects_repo.list_projects(conn)
    if not projects:
        return render(request, "welcome.html", {"nav": "dashboard"})
    project_ids = {p["id"] for p in projects}
    selected = project if project in project_ids else None
    totals = stats_repo.dashboard_totals(conn, selected)
    status_total = sum(totals[k] for k in ("status_2xx", "status_3xx", "status_4xx", "status_5xx", "status_other"))
    context = {
        "nav": "dashboard",
        "projects": projects,
        "selected_project": selected,
        "totals": totals,
        "status_total": status_total,
        "recent": stats_repo.recent_crawls(conn, 8, selected),
        "active": stats_repo.active_crawls(conn),
        "trends": stats_repo.project_trends(conn, selected),
    }
    template = "partials/dashboard_body.html" if request.headers.get("HX-Request") == "true" else "dashboard.html"
    return render(request, template, context)
