"""Masaüstü sürümü (Windows): yerel sunucuyu arka planda başlatıp arayüzü yerel bir pencerede açar.

    python -m zerqon.desktop            # geliştirme ortamında masaüstü penceresi (pywebview gerekir)
    ZerqonSpider.exe                    # PyInstaller paketi (packaging/windows)
    ZerqonSpider.exe --smoke-test       # pencere açmadan sunucuyu doğrular (CI / paket kontrolü)

Güvenlik modeli web sürümüyle aynıdır: sunucu yalnızca 127.0.0.1 üzerinde, boş bir portta dinler.
Aynı veri klasörünü iki örneğin paylaşmaması için tek örnek kilidi kullanılır (yarım taramaların
yanlışlıkla "kesildi" işaretlenmesini önler).
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from pathlib import Path
from typing import IO, Any

from zerqon import PRODUCT_NAME, __version__
from zerqon.config import Settings, get_settings, user_app_dir

logger = logging.getLogger("zerqon.desktop")

LOOPBACK = "127.0.0.1"
PREFERRED_PORT = 47865
WINDOW_SIZE = (1380, 900)
WINDOW_MIN_SIZE = (1000, 640)
STARTUP_TIMEOUT_S = 30.0


def find_free_port(preferred: int = PREFERRED_PORT, host: str = LOOPBACK) -> int:
    """Tercih edilen port boşsa onu (çerezler tutarlı kalsın), değilse işletim sisteminin verdiği boş portu döndürür."""
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
            except OSError:
                continue
            return int(sock.getsockname()[1])
    raise OSError("no free port")


class SingleInstanceLock:
    """Veri klasöründe dosya kilidi; süreç kapanınca işletim sistemi kilidi bırakır."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[bytes] | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 - kilit süreç boyunca açık kalmalı
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._handle.close()
        self._handle = None


class ServerThread:
    """uvicorn sunucusunu ayrı bir thread'de çalıştırır ve hazır olmasını bekler."""

    def __init__(self, settings: Settings) -> None:
        import uvicorn

        from zerqon.web.app import create_app

        config = uvicorn.Config(
            create_app(settings), host=settings.host, port=settings.port,
            log_config=None, log_level="warning", access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="zerqon-server", daemon=True)
        self.url = f"http://{settings.host}:{settings.port}/"

    def start(self, timeout: float = STARTUP_TIMEOUT_S) -> bool:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.started:
                return True
            if not self.thread.is_alive():
                return False
            time.sleep(0.05)
        return False

    def stop(self, timeout: float = 20.0) -> None:
        self.server.should_exit = True
        self.thread.join(timeout)


def show_message(text: str, error: bool = True) -> None:
    """Pencere olmadan kullanıcıya mesaj göster (paketlenmiş sürümde konsol yoktur)."""
    if sys.platform == "win32":
        import ctypes

        flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, text, PRODUCT_NAME, flags)
    else:
        print(text, file=sys.stderr)


def _translator(settings: Settings) -> Any:
    from zerqon.i18n import Translator

    return Translator(settings.default_language)


def prepare_settings(base: Settings | None = None) -> Settings:
    # Masaüstü sürümü hiçbir koşulda ağa açılmaz: .env'deki ZERQON_HOST/PORT yok sayılır.
    settings = (base or get_settings()).model_copy(update={"host": LOOPBACK, "port": find_free_port()})
    settings.ensure_dirs()
    return settings


def smoke_test(server: ServerThread) -> int:
    """Paket doğrulaması: sayfalar, statik dosyalar, şablonlar ve Playwright sürücüsü erişilebilir mi?"""
    import httpx

    from zerqon.browser_setup import driver_available

    checks = {"/": 200, "/settings": 200, "/static/img/logo-mark.svg": 200, "/static/vendor/htmx.min.js": 200}
    with httpx.Client(base_url=server.url, trust_env=False, timeout=15) as client:
        for path, expected in checks.items():
            status = client.get(path).status_code
            if status != expected:
                logger.error("Smoke test: %s → %s (beklenen %s)", path, status, expected)
                return 1
    if not driver_available():
        logger.error("Smoke test: Playwright sürücüsü pakette yok.")
        return 1
    logger.info("Smoke test başarılı: %s", server.url)
    return 0


def main(argv: list[str] | None = None, base_settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ZerqonSpider", description=f"{PRODUCT_NAME} {__version__} — desktop")
    parser.add_argument("--smoke-test", action="store_true", help="Pencere açmadan sunucuyu başlat, doğrula ve çık")
    parser.add_argument("--debug", action="store_true", help="WebView geliştirici araçlarını etkinleştir")
    args = parser.parse_args(argv)

    settings = prepare_settings(base_settings)
    t = _translator(settings)
    lock = SingleInstanceLock(settings.resolved_data_dir / ".zerqon-desktop.lock")
    if not lock.acquire():
        if not args.smoke_test:
            show_message(t("desktop.already_running"), error=False)
        return 2

    try:
        try:
            server = ServerThread(settings)
            started = server.start()
        except Exception as exc:  # noqa: BLE001 - kullanıcıya gösterilecek
            logger.exception("Sunucu oluşturulamadı")
            started, error = False, str(exc)
        else:
            error = "timeout"
        if not started:
            if not args.smoke_test:
                show_message(t("desktop.start_failed", logs=str(settings.logs_dir), error=error))
            return 1

        try:
            if args.smoke_test:
                return smoke_test(server)
            return run_window(server, settings, debug=args.debug, t=t)
        finally:
            server.stop()
    finally:
        lock.release()


def fit_window(webview: Any) -> tuple[int, int]:
    """Varsayılan pencere boyutunu birincil ekrana sığdırır (küçük dizüstü ekranlarında taşmasın)."""
    width, height = WINDOW_SIZE
    try:
        screen = webview.screens[0]
        width = min(width, int(screen.width * 0.92))
        height = min(height, int(screen.height * 0.88))
    except Exception:  # noqa: BLE001 - ekran bilgisi alınamazsa varsayılan
        pass
    return max(width, WINDOW_MIN_SIZE[0]), max(height, WINDOW_MIN_SIZE[1])


def run_window(server: ServerThread, settings: Settings, debug: bool, t: Any) -> int:
    import webview

    if sys.platform == "win32":
        # WebView2 yoksa pywebview sessizce eski IE motoruna (mshtml) düşer; arayüz orada çalışmaz.
        try:
            from webview.platforms import winforms

            renderer = getattr(winforms, "renderer", "unknown")
        except Exception as exc:  # noqa: BLE001 - pythonnet/.NET yüklenemedi
            renderer = f"{type(exc).__name__}: {exc}"
        if renderer != "edgechromium":
            logger.error("WebView2 kullanılamıyor (renderer=%s)", renderer)
            show_message(t("desktop.webview2_missing", error=f"renderer={renderer}"[:300]))
            return 1

    webview.settings["ALLOW_DOWNLOADS"] = True  # CSV / HTML rapor / yedek indirmeleri
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # taranan sitelere bağlantılar sistem tarayıcısında
    width, height = fit_window(webview)
    webview.create_window(
        PRODUCT_NAME, server.url,
        width=width, height=height, min_size=WINDOW_MIN_SIZE,
        background_color="#0A1120", text_select=True,
    )
    try:
        webview.start(
            gui="edgechromium" if sys.platform == "win32" else None,
            debug=debug,
            private_mode=False,  # dil/tema çerezleri oturumlar arasında korunur
            storage_path=str(user_app_dir() / "webview"),
        )
    except Exception as exc:  # noqa: BLE001 - WebView2 eksikliği vb.
        logger.exception("Pencere açılamadı")
        show_message(t("desktop.webview2_missing", error=str(exc)[:300]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
