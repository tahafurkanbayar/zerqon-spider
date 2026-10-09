"""Route modüllerinin kaydı."""

from __future__ import annotations

from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    from zerqon.web.routes import crawls, dashboard, preferences, projects

    app.include_router(dashboard.router)
    app.include_router(projects.router)
    app.include_router(preferences.router)
    app.include_router(crawls.router)
