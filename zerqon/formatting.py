"""Şablonlarda ve raporlarda ortak kullanılan biçimlendirme yardımcıları (iş mantığı içermez)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


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
