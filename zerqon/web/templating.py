"""Jinja2 şablon ortamı, filtreler ve render yardımcısı.

Şablonlarda iş mantığı bulunmaz; yalnızca biçimlendirme filtreleri burada tanımlanır.
Autoescape her zaman açıktır — hedef sitelerden gelen veri güvenilmezdir.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from zerqon import PRODUCT_DESCRIPTION, PRODUCT_NAME, SLOGAN, __version__
from zerqon.i18n import Translator

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
env = templates.env
env.autoescape = True
env.trim_blocks = True
env.lstrip_blocks = True

SEVERITY_ORDER: tuple[str, ...] = ("critical", "high", "medium", "low", "info")


def fmt_number(value: Any, lang: str = "tr") -> str:
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        text = f"{int(number):,}"
    else:
        text = f"{number:,.1f}"
    if lang == "tr":
        text = text.replace(",", " ").replace(".", ",")
    return text


def fmt_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.astimezone().strftime("%d.%m.%Y %H:%M")


def fmt_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def fmt_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def status_class(code: int | None) -> str:
    if code is None:
        return "st-err"
    if 200 <= code < 300:
        return "st-2xx"
    if 300 <= code < 400:
        return "st-3xx"
    if 400 <= code < 500:
        return "st-4xx"
    if code >= 500:
        return "st-5xx"
    return "st-err"


def truncate_middle(value: str | None, length: int = 80) -> str:
    if not value:
        return ""
    if len(value) <= length:
        return value
    half = (length - 1) // 2
    return f"{value[:half]}…{value[-half:]}"


_ICONS: dict[str, str] = {
    "dashboard": '<path d="M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z"/>',
    "projects": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "compare": '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
    "crawl": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "issues": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4m0 4h.01"/>',
    "pages": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "report": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "play": '<path d="m6 4 14 8-14 8z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    "external": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/>',
    "trash": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/>',
    "backup": '<path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "edit": '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "resume": '<path d="M1 4v6h6M3.5 15a9 9 0 1 0 2.1-9.4L1 10"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
    "code": '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
}


def icon(name: str, size: int = 18, cls: str = "") -> Markup:
    body = _ICONS.get(name, _ICONS["info"])
    return Markup(  # noqa: S704 - sabit, güvenilir SVG içeriği
        f'<svg class="icon {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{body}</svg>'
    )


env.filters.update(
    number=fmt_number,
    dt=fmt_datetime,
    duration=fmt_duration,
    bytes=fmt_bytes,
    status_class=status_class,
    middle=truncate_middle,
)
env.globals.update(
    PRODUCT_NAME=PRODUCT_NAME,
    SLOGAN=SLOGAN,
    PRODUCT_DESCRIPTION=PRODUCT_DESCRIPTION,
    VERSION=__version__,
    SEVERITY_ORDER=SEVERITY_ORDER,
    icon=icon,
)


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    ctx: dict[str, Any] = dict(context or {})
    t: Translator = getattr(request.state, "t", None) or Translator()
    ctx.setdefault("t", t)
    ctx.setdefault("lang", t.language)
    ctx.setdefault("theme", getattr(request.state, "theme", "system"))
    ctx.setdefault("is_htmx", request.headers.get("HX-Request") == "true")
    return templates.TemplateResponse(request, template, ctx, status_code=status_code, headers=headers)
