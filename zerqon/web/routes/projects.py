"""Proje yönetimi: liste, oluşturma, düzenleme, tarama ayarları, silme."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError

from zerqon.db.repositories import crawls_repo, projects_repo, settings_repo
from zerqon.schemas import BOOL_SETTINGS, CrawlSettingsModel, ProjectCreate
from zerqon.web.deps import get_conn, parse_form, redirect, require, validation_messages
from zerqon.web.templating import render

router = APIRouter(prefix="/projects")


@router.get("", response_class=HTMLResponse)
def list_projects(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    return render(
        request,
        "projects/list.html",
        {"nav": "projects", "projects": projects_repo.list_projects(conn), "msg": request.query_params.get("msg", "")},
    )


@router.get("/new", response_class=HTMLResponse)
def new_project(request: Request) -> HTMLResponse:
    return render(
        request,
        "projects/form.html",
        {"nav": "projects", "form": {}, "errors": {}, "settings": CrawlSettingsModel(), "project": None},
    )


@router.post("/new", response_model=None)
async def create_project(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    form: dict[str, Any] = dict(await request.form())
    errors: dict[str, str] = {}
    project_data: ProjectCreate | None = None
    settings: CrawlSettingsModel | None = None
    try:
        project_data = ProjectCreate.model_validate({"name": form.get("name", ""), "start_url": form.get("start_url", "")})
    except ValidationError as exc:
        errors.update(validation_messages(exc))
    try:
        settings = parse_form(CrawlSettingsModel, _settings_fields(form), BOOL_SETTINGS)
    except ValidationError as exc:
        errors.update(validation_messages(exc))
    if errors or project_data is None or settings is None:
        return render(
            request,
            "projects/form.html",
            {"nav": "projects", "form": form, "errors": errors, "settings": _settings_echo(form), "project": None},
            status_code=422,
        )
    project_id = projects_repo.create_project(conn, project_data, settings)
    return redirect(f"/projects/{project_id}?msg=flash.project_created", request)


@router.get("/{project_id}", response_class=HTMLResponse)
def project_detail(project_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    project = require(projects_repo.get_project(conn, project_id))
    settings = settings_repo.get_settings(conn, project["settings_id"])
    jobs = crawls_repo.list_jobs(conn, project_id)
    return render(
        request,
        "projects/detail.html",
        {
            "nav": "projects",
            "project": project,
            "settings": settings,
            "jobs": jobs,
            "active_job": next((j for j in jobs if j["status"] in crawls_repo.ACTIVE_STATUSES), None),
            "msg": request.query_params.get("msg", ""),
        },
    )


@router.get("/{project_id}/edit", response_class=HTMLResponse)
def edit_project(project_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> HTMLResponse:
    project = require(projects_repo.get_project(conn, project_id))
    settings = settings_repo.get_settings(conn, project["settings_id"])
    return render(
        request,
        "projects/form.html",
        {"nav": "projects", "form": project, "errors": {}, "settings": settings, "project": project},
    )


@router.post("/{project_id}/edit", response_model=None)
async def update_project(project_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    project = require(projects_repo.get_project(conn, project_id))
    form: dict[str, Any] = dict(await request.form())
    errors: dict[str, str] = {}
    try:
        project_data = ProjectCreate.model_validate({"name": form.get("name", ""), "start_url": form.get("start_url", "")})
    except ValidationError as exc:
        errors.update(validation_messages(exc))
    try:
        settings = parse_form(CrawlSettingsModel, _settings_fields(form), BOOL_SETTINGS)
    except ValidationError as exc:
        errors.update(validation_messages(exc))
    if errors:
        return render(
            request,
            "projects/form.html",
            {"nav": "projects", "form": form, "errors": errors, "settings": _settings_echo(form), "project": project},
            status_code=422,
        )
    projects_repo.update_project(conn, project_id, project_data)
    settings_repo.update_settings(conn, project["settings_id"], settings)
    return redirect(f"/projects/{project_id}?msg=flash.project_saved", request)


@router.post("/{project_id}/delete", response_model=None)
def delete_project(project_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    require(projects_repo.get_project(conn, project_id))
    active = [j for j in crawls_repo.list_jobs(conn, project_id) if j["status"] in crawls_repo.ACTIVE_STATUSES]
    if active:
        return redirect(f"/projects/{project_id}?msg=flash.project_busy", request)
    projects_repo.delete_project(conn, project_id)
    return redirect("/projects?msg=flash.project_deleted", request)


def _settings_fields(form: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in form.items() if k in CrawlSettingsModel.model_fields}


def _settings_echo(form: dict[str, Any]) -> dict[str, Any]:
    """Hatalı form tekrar gösterilirken kullanıcının girdiği değerleri korur."""
    echo: dict[str, Any] = CrawlSettingsModel().model_dump()
    for key in CrawlSettingsModel.model_fields:
        if key in BOOL_SETTINGS:
            echo[key] = form.get(key) in ("on", "true", "1")
        elif key in form:
            echo[key] = form[key]
    return echo
