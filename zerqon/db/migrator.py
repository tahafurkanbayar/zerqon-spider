"""Sürümlü SQL migration sistemi.

Migration dosyaları `migrations/NNNN_aciklama.sql` biçimindedir ve sırayla, her biri
tek bir işlem içinde uygulanır. Uygulanan sürümler `schema_migrations` tablosunda tutulur.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from zerqon.db.connection import utcnow_iso

logger = logging.getLogger("zerqon.db")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_FILENAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME_RE.match(path.name)
        if not match:
            raise ValueError(f"Geçersiz migration dosya adı: {path.name}")
        migrations.append(Migration(int(match.group(1)), path.stem, path.read_text(encoding="utf-8")))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError("Yinelenen migration sürümü bulundu")
    return migrations


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def latest_version(directory: Path = MIGRATIONS_DIR) -> int:
    migrations = discover_migrations(directory)
    return migrations[-1].version if migrations else 0


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[int]:
    """Bekleyen migration'ları uygular, uygulanan sürümleri döndürür."""
    applied: list[int] = []
    version = current_version(conn)
    for migration in discover_migrations(directory):
        if migration.version <= version:
            continue
        logger.info("Migration uygulanıyor: %s", migration.name)
        script = (
            "BEGIN;\n"
            f"{migration.sql}\n;\n"
            "INSERT INTO schema_migrations(version, name, applied_at) "
            f"VALUES ({migration.version}, '{migration.name}', '{utcnow_iso()}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        applied.append(migration.version)
    return applied
