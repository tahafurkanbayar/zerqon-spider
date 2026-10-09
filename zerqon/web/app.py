"""FastAPI uygulama fabrikası."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from zerqon import PRODUCT_NAME, __version__
from zerqon.config import Settings, get_settings
from zerqon.db.connection import Database
from zerqon.db.migrator import migrate
from zerqon.db.repositories import crawls_repo, settings_repo
from zerqon.i18n import Translator, normalize_language
from zerqon.logging_config import setup_logging
from zerqon.web.templating import render

logger = logging.getLogger("zerqon.web")

STATIC_DIR = Path(__file__).parent / "static"
LANG_COOKIE = "zq_lang"
THEME_COOKIE = "zq_theme"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _allowed_hosts(settings: Settings) -> list[str]:
    hosts = {"127.0.0.1", "localhost", "[::1]", "::1", "testserver"}
    if settings.host not in ("0.0.0.0", "::"):
        hosts.add(settings.host)
    else:
        logger.warning("Sunucu tüm ağ arayüzlerini dinliyor; Host kontrolü devre dışı.")
        return ["*"]
    return sorted(hosts)


def init_database(settings: Settings) -> Database:
    settings.ensure_dirs()
    db = Database(settings.db_path)
    with db.session() as conn:
        migrate(conn)
        interrupted = crawls_repo.mark_running_as_interrupted(conn)
        if interrupted:
            logger.warning("Yarım kalmış %d tarama 'interrupted' olarak işaretlendi.", interrupted)
    return db


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    db = init_database(settings)

    from zerqon.crawler.manager import CrawlManager

    manager = CrawlManager(db, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("%s %s başlatıldı — veri dizini: %s", PRODUCT_NAME, __version__, settings.resolved_data_dir)
        yield
        manager.shutdown()

    app = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.manager = manager

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Yerel CSRF koruması: durum değiştiren isteklerde köken aynı host olmalı
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin") or request.headers.get("referer")
            if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
                logger.warning("Farklı kökenli istek reddedildi: %s %s", request.method, request.url.path)
                return PlainTextResponse("Cross-origin request rejected", status_code=403)

        lang_cookie = request.cookies.get(LANG_COOKIE)
        if lang_cookie:
            language = normalize_language(lang_cookie)
        else:
            with db.session() as conn:
                language = normalize_language(
                    settings_repo.get_app_setting(conn, "language", settings.default_language)
                )
        request.state.t = Translator(language)
        theme = request.cookies.get(THEME_COOKIE, "system")
        request.state.theme = theme if theme in ("light", "dark", "system") else "system"

        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts(settings))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from zerqon.web.routes import register_routes

    register_routes(app)
    _register_error_handlers(app)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if request.url.path.startswith("/api/"):
            return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
        key = "errors.not_found" if exc.status_code == 404 else "errors.generic"
        return render(
            request,
            "error.html",
            {"status": exc.status_code, "message_key": key, "detail": exc.detail if exc.status_code != 404 else None},
            status_code=exc.status_code,
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def db_error(request: Request, exc: sqlite3.OperationalError) -> Response:
        logger.exception("Veritabanı hatası")
        text = str(exc).lower()
        if "disk" in text and "full" in text:
            key = "errors.disk_full"
        elif "locked" in text or "busy" in text:
            key = "errors.db_locked"
        else:
            key = "errors.db_generic"
        return render(request, "error.html", {"status": 503, "message_key": key}, status_code=503)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> Response:
        logger.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
        return render(request, "error.html", {"status": 500, "message_key": "errors.generic"}, status_code=500)
