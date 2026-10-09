"""crawl_settings ve app_settings tabloları."""

from __future__ import annotations

import sqlite3

from zerqon.db.connection import utcnow_iso
from zerqon.schemas import BOOL_SETTINGS, SETTINGS_FIELDS, CrawlSettingsModel


def insert_settings(conn: sqlite3.Connection, settings: CrawlSettingsModel) -> int:
    data = settings.model_dump()
    columns = list(SETTINGS_FIELDS) + ["created_at"]
    values = [int(data[f]) if f in BOOL_SETTINGS else data[f] for f in SETTINGS_FIELDS] + [utcnow_iso()]
    placeholders = ", ".join("?" for _ in columns)
    cur = conn.execute(
        f"INSERT INTO crawl_settings ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608 - sabit sütunlar
        values,
    )
    return int(cur.lastrowid or 0)


def update_settings(conn: sqlite3.Connection, settings_id: int, settings: CrawlSettingsModel) -> None:
    data = settings.model_dump()
    assignments = ", ".join(f"{f} = ?" for f in SETTINGS_FIELDS)
    values = [int(data[f]) if f in BOOL_SETTINGS else data[f] for f in SETTINGS_FIELDS]
    conn.execute(f"UPDATE crawl_settings SET {assignments} WHERE id = ?", [*values, settings_id])  # noqa: S608


def get_settings(conn: sqlite3.Connection, settings_id: int) -> CrawlSettingsModel:
    row = conn.execute("SELECT * FROM crawl_settings WHERE id = ?", (settings_id,)).fetchone()
    if row is None:
        raise LookupError(f"crawl_settings {settings_id} bulunamadı")
    data = {f: row[f] for f in SETTINGS_FIELDS}
    for name in BOOL_SETTINGS:
        data[name] = bool(data[name])
    # Kayıtlı ayarlar zaten doğrulanmıştı; model_construct ile tekrar doğrulama yapılmaz
    return CrawlSettingsModel.model_construct(**data)


def get_app_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_app_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
