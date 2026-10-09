"""`python -m zerqon` — veritabanını hazırlar ve yerel sunucuyu başlatır."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from zerqon import PRODUCT_NAME, SLOGAN, __version__
from zerqon.config import get_settings


def _utf8_stdio() -> None:
    """Çıktı dosyaya/boruya yönlendirildiğinde Türkçe karakterler bozulmasın (Windows yerel kod sayfası)."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(prog="zerqon", description=f"{PRODUCT_NAME} — {SLOGAN}")
    parser.add_argument("--host", help="Dinlenecek adres (varsayılan .env / 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Port (varsayılan .env / 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    parser.add_argument("--migrate-only", action="store_true", help="Yalnızca veritabanı migration'larını uygula")
    parser.add_argument("--backup", metavar="DOSYA", nargs="?", const="", help="Veritabanı yedeği al (.zip)")
    parser.add_argument("--restore", metavar="DOSYA", help="Yedekten geri yükle (.zip)")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port

    from zerqon.web.app import init_database

    db = init_database(settings)
    if args.migrate_only:
        print(f"Veritabanı hazır: {settings.db_path}")
        return 0
    if args.backup is not None:
        from zerqon.reports.backup import create_backup

        path = create_backup(db, settings.backups_dir, target=args.backup or None)
        print(f"Yedek oluşturuldu: {path}")
        return 0
    if args.restore:
        from zerqon.reports.backup import restore_backup

        restore_backup(db, args.restore)
        print("Geri yükleme tamamlandı.")
        return 0

    import uvicorn

    from zerqon.web.app import create_app

    url = f"http://{'127.0.0.1' if settings.host in ('0.0.0.0', '::') else settings.host}:{settings.port}/"
    print(f"\n  {PRODUCT_NAME} v{__version__} — {SLOGAN}\n  Arayüz: {url}\n  Durdurmak için Ctrl+C\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
