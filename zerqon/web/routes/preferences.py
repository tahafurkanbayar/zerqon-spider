"""Arayüz tercihleri (dil, tema) ve uygulama ayarları sayfası."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from zerqon.config import Settings
from zerqon.db.repositories import settings_repo
from zerqon.i18n import SUPPORTED_LANGUAGES
from zerqon.reports.backup import list_backups
from zerqon.web.app import LANG_COOKIE, THEME_COOKIE
from zerqon.web.deps import get_app_settings, get_conn, redirect
from zerqon.web.templating import render

router = APIRouter()

_COOKIE_MAX_AGE = 365 * 24 * 3600


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, app_settings: Settings = Depends(get_app_settings)) -> HTMLResponse:
    return render(
        request,
        "settings.html",
        {
            "nav": "settings",
            "data_dir": str(app_settings.resolved_data_dir),
            "db_path": str(app_settings.db_path),
            "logs_dir": str(app_settings.logs_dir),
            "allow_localhost": app_settings.allow_localhost,
            "bind": f"{app_settings.host}:{app_settings.port}",
            "msg": request.query_params.get("msg", ""),
            "backups": list_backups(app_settings.backups_dir)[:20],
            "backups_dir": str(app_settings.backups_dir),
        },
    )


@router.post("/preferences/language")
def set_language(
    request: Request,
    language: str = Form(...),
    next_url: str = Form("/", alias="next"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Response:
    language = language if language in SUPPORTED_LANGUAGES else "tr"
    settings_repo.set_app_setting(conn, "language", language)
    response = redirect(_safe_next(next_url), request)
    response.set_cookie(LANG_COOKIE, language, max_age=_COOKIE_MAX_AGE, samesite="strict", httponly=True)
    return response


@router.post("/preferences/theme")
def set_theme(request: Request, theme: str = Form(...)) -> Response:
    theme = theme if theme in ("light", "dark", "system") else "system"
    response = Response(status_code=204)
    response.set_cookie(THEME_COOKIE, theme, max_age=_COOKIE_MAX_AGE, samesite="strict")
    return response


def _safe_next(value: str) -> str:
    """Açık yönlendirmeyi önler: yalnızca site içi göreli yollar."""
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"
