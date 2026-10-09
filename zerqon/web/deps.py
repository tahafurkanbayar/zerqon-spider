"""FastAPI bağımlılıkları ve form yardımcıları."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ValidationError

from zerqon.config import Settings
from zerqon.db.connection import Database


def get_db(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    db: Database = request.app.state.db
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def require(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        raise HTTPException(status_code=404)
    return value


def validation_messages(exc: ValidationError) -> dict[str, str]:
    """Pydantic hatalarını alan → mesaj sözlüğüne çevirir."""
    messages: dict[str, str] = {}
    for err in exc.errors():
        field = str(err["loc"][0]) if err.get("loc") else "__all__"
        msg = str(err.get("msg", ""))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        messages.setdefault(field, msg)
    return messages


def parse_form(model: type[BaseModel], form: dict[str, Any], bool_fields: frozenset[str] = frozenset()) -> Any:
    data = {k: v for k, v in form.items() if v != "" or k in ("include_patterns", "exclude_patterns")}
    for name in bool_fields:
        data[name] = form.get(name) in ("on", "true", "1", "yes")
    return model.model_validate(data)


def redirect(url: str, request: Request | None = None) -> Response:
    """HTMX isteklerinde HX-Redirect, normal isteklerde 303 yönlendirmesi."""
    if request is not None and request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)
