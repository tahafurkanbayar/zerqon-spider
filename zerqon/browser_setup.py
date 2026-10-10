"""JavaScript render motoru (Playwright Chromium headless shell) kurulum durumu ve arka planda kurulum.

Masaüstü sürümü Chromium'u pakete gömmez (~100 MB); kullanıcı Ayarlar ekranından ilk kullanımda indirir.
Kurulum Playwright'ın kendi sürücüsüyle (`playwright install --only-shell chromium`) yapılır; tarama
`chromium.launch(headless=True)` ile headless shell'i kullandığı için tam Chromium gerekmez.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("zerqon.browser_setup")

INSTALL_ARGS = ("install", "--only-shell", "--no-progress", "chromium")
_LOCATION_RE = re.compile(r"^\s*Install location:\s*(.+?)\s*$", re.MULTILINE)
_SHELL_DIR_RE = re.compile(r"chromium_headless_shell-\d+$")
_STATUS_TTL_S = 30.0


def _driver_command(*args: str) -> tuple[list[str], dict[str, str]]:
    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    return [str(node), str(cli), *args], get_driver_env()


def _run_driver(*args: str, timeout: float) -> subprocess.CompletedProcess[str]:
    cmd, env = _driver_command(*args)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(
        cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=flags, stdin=subprocess.DEVNULL,
    )


def headless_shell_dir() -> Path | None:
    """Bu Playwright sürümünün beklediği headless shell klasörü (PLAYWRIGHT_BROWSERS_PATH dikkate alınır)."""
    result = _run_driver("install", "--dry-run", "--only-shell", "chromium", timeout=60)
    for location in _LOCATION_RE.findall(result.stdout):
        path = Path(location)
        if _SHELL_DIR_RE.search(path.name):
            return path
    return None


def is_installed_at(path: Path | None) -> bool:
    return path is not None and (path / "INSTALLATION_COMPLETE").is_file()


@dataclass
class BrowserStatus:
    installed: bool
    state: str  # idle | running | done | failed
    location: str | None
    error: str | None


class BrowserInstaller:
    """Tek seferde tek kurulum; durum web arayüzünden sorgulanır."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = "idle"
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._cached: tuple[float, Path | None, bool] | None = None

    def _probe(self, force: bool = False) -> tuple[Path | None, bool]:
        now = time.monotonic()
        if not force and self._cached and now - self._cached[0] < _STATUS_TTL_S:
            return self._cached[1], self._cached[2]
        try:
            location = headless_shell_dir()
        except Exception as exc:  # noqa: BLE001 - sürücü eksik/bozuk olabilir
            logger.warning("Playwright sürücüsü sorgulanamadı: %s", exc)
            location = None
        installed = is_installed_at(location)
        self._cached = (now, location, installed)
        return location, installed

    def status(self) -> BrowserStatus:
        with self._lock:
            state, error = self._state, self._error
        location, installed = self._probe(force=state == "done")
        return BrowserStatus(installed, state, str(location) if location else None, error)

    def start(self) -> bool:
        """Kurulumu arka planda başlatır; zaten sürüyorsa False döner."""
        with self._lock:
            if self._state == "running":
                return False
            self._state, self._error = "running", None
            self._thread = threading.Thread(target=self._install, name="zerqon-browser-install", daemon=True)
            self._thread.start()
            return True

    def _install(self) -> None:
        logger.info("Chromium headless shell kurulumu başladı.")
        error: str | None = None
        try:
            result = _run_driver(*INSTALL_ARGS, timeout=1800)
            if result.returncode != 0:
                lines = (result.stderr or result.stdout).strip().splitlines()
                error = lines[-1] if lines else f"exit {result.returncode}"
        except (OSError, subprocess.SubprocessError) as exc:
            error = str(exc)
        ok = error is None
        with self._lock:
            self._state = "done" if ok else "failed"
            self._error = None if ok else error[:300]
            self._cached = None
        if ok:
            logger.info("Chromium headless shell kuruldu.")
        else:
            logger.error("Chromium kurulumu başarısız: %s", self._error)

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)


def driver_available() -> bool:
    """Playwright sürücüsü (node + cli.js) pakette mevcut mu? (masaüstü paketi doğrulaması için)"""
    try:
        cmd, _ = _driver_command()
    except Exception:  # noqa: BLE001
        return False
    return all(os.path.isfile(part) for part in cmd[:2])
