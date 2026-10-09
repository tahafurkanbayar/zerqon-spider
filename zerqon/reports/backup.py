"""Yedekleme ve geri yükleme.

Yedek = `.zip` içinde:
  - `zerqon.db`      : SQLite online backup API ile alınmış tutarlı anlık görüntü (WAL dahil)
  - `manifest.json`  : uygulama/şema sürümü, oluşturulma zamanı, kayıt sayıları
Geri yükleme:
  1. Zip üyeleri ve boyutları doğrulanır (yol enjeksiyonu / zip bombası yok)
  2. Veritabanı geçici dizine çıkarılır, `PRAGMA integrity_check` ve şema sürümü kontrol edilir
  3. Mevcut veritabanının güvenlik kopyası `backups/pre-restore-*.zip` olarak alınır
  4. İçerik SQLite backup API ile canlı veritabanına aktarılır ve bekleyen migration'lar uygulanır
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from zerqon import PRODUCT_NAME, __version__
from zerqon.db.connection import Database, utcnow_iso
from zerqon.db.migrator import current_version, latest_version, migrate

DB_MEMBER = "zerqon.db"
MANIFEST_MEMBER = "manifest.json"
MAX_DB_BYTES = 20 * 1024**3


class BackupError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 - sabit tablo adları
        for table in ("projects", "crawl_jobs", "pages", "issues", "reports")
    }


def create_backup(db: Database, backups_dir: Path, target: str | Path | None = None, prefix: str = "zerqon-backup") -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow_iso().replace(":", "").replace("-", "").replace("+0000", "")
    path = Path(target) if target else backups_dir / f"{prefix}-{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / DB_MEMBER
        source = db.connect()
        try:
            dest = sqlite3.connect(snapshot)
            try:
                source.backup(dest)
                dest.execute("PRAGMA journal_mode=DELETE")
                manifest = {
                    "product": PRODUCT_NAME,
                    "app_version": __version__,
                    "schema_version": current_version(dest),
                    "created_at": utcnow_iso(),
                    "counts": _counts(dest),
                }
            finally:
                dest.close()
        finally:
            source.close()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, DB_MEMBER)
            archive.writestr(MANIFEST_MEMBER, json.dumps(manifest, ensure_ascii=False, indent=2))
    return path


def read_manifest(path: str | Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if names != {DB_MEMBER, MANIFEST_MEMBER}:
                raise BackupError("invalid_archive", ", ".join(sorted(names))[:200])
            info = archive.getinfo(DB_MEMBER)
            if info.file_size > MAX_DB_BYTES:
                raise BackupError("too_large")
            manifest = json.loads(archive.read(MANIFEST_MEMBER).decode("utf-8"))
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
        raise BackupError("invalid_archive", str(exc)) from exc
    if not isinstance(manifest, dict) or manifest.get("product") != PRODUCT_NAME:
        raise BackupError("not_zerqon_backup")
    return manifest


def restore_backup(db: Database, path: str | Path, backups_dir: Path | None = None) -> dict[str, Any]:
    manifest = read_manifest(path)
    if int(manifest.get("schema_version", 0)) > latest_version():
        raise BackupError("newer_schema", str(manifest.get("schema_version")))
    with tempfile.TemporaryDirectory() as tmp:
        extracted = Path(tmp) / DB_MEMBER
        with zipfile.ZipFile(path) as archive, archive.open(DB_MEMBER) as src, extracted.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        candidate = sqlite3.connect(extracted)
        try:
            check = candidate.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise BackupError("integrity_failed", str(check))
            tables = {r[0] for r in candidate.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"projects", "crawl_jobs", "pages", "schema_migrations"} <= tables:
                raise BackupError("not_zerqon_backup")
            if backups_dir is not None:
                create_backup(db, backups_dir, prefix="pre-restore")
            live = db.connect()
            try:
                candidate.backup(live)
                migrate(live)
            finally:
                live.close()
        except sqlite3.DatabaseError as exc:
            raise BackupError("invalid_database", str(exc)) from exc
        finally:
            candidate.close()
    return manifest


def list_backups(backups_dir: Path) -> list[dict[str, Any]]:
    if not backups_dir.exists():
        return []
    items = []
    for path in sorted(backups_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append({"name": path.name, "size": path.stat().st_size, "mtime": path.stat().st_mtime})
    return items
