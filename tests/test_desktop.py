"""Masaüstü sürümü: veri konumu, port seçimi, tek örnek kilidi, sunucu yaşam döngüsü ve Chromium kurulum akışı."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from zerqon import browser_setup, config, desktop
from zerqon.browser_setup import BrowserInstaller, BrowserStatus
from zerqon.config import Settings


def test_frozen_build_uses_user_app_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.config_root() == config.PROJECT_ROOT  # kaynak koddan çalışırken proje kökü
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert config.config_root() == tmp_path / "Zerqon Spider"
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.resolved_data_dir == (tmp_path / "Zerqon Spider" / "data").resolve()


def test_find_free_port_prefers_fixed_port_and_falls_back() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        preferred = probe.getsockname()[1]
    assert desktop.find_free_port(preferred) == preferred
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", preferred))
        busy.listen()
        other = desktop.find_free_port(preferred)
        assert other != preferred and other > 0


def test_single_instance_lock(tmp_path: Path) -> None:
    first = desktop.SingleInstanceLock(tmp_path / "app.lock")
    second = desktop.SingleInstanceLock(tmp_path / "app.lock")
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_desktop_settings_never_listen_on_network(tmp_path: Path) -> None:
    base = Settings(_env_file=None, data_dir=tmp_path, host="0.0.0.0", port=80)  # type: ignore[call-arg]
    prepared = desktop.prepare_settings(base)
    assert prepared.host == "127.0.0.1" and prepared.port != 80
    assert base.host == "0.0.0.0"  # ortak ayar nesnesi değiştirilmez


def test_smoke_test_mode_starts_and_stops_server(tmp_path: Path) -> None:
    base = Settings(_env_file=None, data_dir=tmp_path)  # type: ignore[call-arg]
    assert desktop.main(["--smoke-test"], base_settings=base) == 0
    # Kilit bırakıldı ve sunucu kapandı: ikinci çalıştırma da başarılı olmalı
    assert desktop.main(["--smoke-test"], base_settings=base) == 0


def test_second_instance_is_refused(tmp_path: Path) -> None:
    base = Settings(_env_file=None, data_dir=tmp_path)  # type: ignore[call-arg]
    holder = desktop.SingleInstanceLock(tmp_path / ".zerqon-desktop.lock")
    assert holder.acquire()
    try:
        assert desktop.main(["--smoke-test"], base_settings=base) == 2
    finally:
        holder.release()


def test_server_thread_serves_only_loopback(tmp_path: Path) -> None:
    settings = desktop.prepare_settings(Settings(_env_file=None, data_dir=tmp_path))  # type: ignore[call-arg]
    server = desktop.ServerThread(settings)
    assert server.start()
    try:
        assert httpx.get(server.url, trust_env=False).status_code == 200
        bad_host = httpx.get(server.url, headers={"Host": "evil.example"}, trust_env=False)
        assert bad_host.status_code == 400
    finally:
        server.stop()
    assert not server.thread.is_alive()


# --- Chromium kurulumu ---------------------------------------------------------------------------

DRY_RUN = """Chrome Headless Shell 153.0 (playwright chromium-headless-shell v1243)
  Install location:    {shell}
  Download url:        https://example.invalid/shell.zip

FFmpeg (playwright ffmpeg v1011)
  Install location:    {ffmpeg}
"""


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_headless_shell_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shell = tmp_path / "chromium_headless_shell-1243"
    output = DRY_RUN.format(shell=shell, ffmpeg=tmp_path / "ffmpeg-1011")
    monkeypatch.setattr(browser_setup, "_run_driver", lambda *a, **k: _completed(output))
    assert browser_setup.headless_shell_dir() == shell
    assert not browser_setup.is_installed_at(shell)
    shell.mkdir()
    (shell / "INSTALLATION_COMPLETE").write_text("")
    assert browser_setup.is_installed_at(shell)


def test_installer_reports_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_driver(*args: str, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if "--dry-run" in args:
            return _completed(DRY_RUN.format(shell=tmp_path / "chromium_headless_shell-1", ffmpeg=tmp_path / "f"))
        return _completed(returncode=1, stderr="Error: download failed\nECONNRESET")

    monkeypatch.setattr(browser_setup, "_run_driver", fake_driver)
    installer = BrowserInstaller()
    assert installer.start()
    installer.wait(10)
    status = installer.status()
    assert status.state == "failed" and not status.installed
    assert status.error == "ECONNRESET"
    assert browser_setup.INSTALL_ARGS in calls  # yalnızca headless shell indirilir


def test_driver_is_available() -> None:
    assert browser_setup.driver_available()


class FakeInstaller:
    def __init__(self) -> None:
        self.state = "idle"
        self.started = 0

    def status(self) -> BrowserStatus:
        return BrowserStatus(self.state == "done", self.state, None, None)

    def start(self) -> bool:
        self.started += 1
        self.state = "running"
        return True


def test_browser_settings_ui(client: TestClient) -> None:
    fake = FakeInstaller()
    client.app.state.browser_installer = fake  # type: ignore[attr-defined]
    page = client.get("/settings")
    assert 'hx-get="/settings/browser"' in page.text

    missing = client.get("/settings/browser")
    assert 'hx-post="/settings/browser/install"' in missing.text
    assert "every 2s" not in missing.text

    running = client.post("/settings/browser/install")
    assert fake.started == 1
    assert "every 2s" in running.text  # kurulum sürerken kendini yeniler

    fake.state = "done"
    done = client.get("/settings/browser")
    assert "every 2s" not in done.text and "status-completed" in done.text


def test_browser_install_requires_same_origin(client: TestClient) -> None:
    fake = FakeInstaller()
    client.app.state.browser_installer = fake  # type: ignore[attr-defined]
    res = client.post("/settings/browser/install", headers={"Origin": "http://evil.example"})
    assert res.status_code == 403 and fake.started == 0

