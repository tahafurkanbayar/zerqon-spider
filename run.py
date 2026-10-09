#!/usr/bin/env python3
"""Zerqon Spider — tek komutlu başlatıcı.

    python run.py            # kur (gerekirse) ve başlat
    python run.py --dev      # test bağımlılıklarını da kur
    python run.py --no-browser --port 9000

İlk çalıştırmada:
  1. Python 3.12/3.13 yorumlayıcısını bulur, `.venv` sanal ortamını oluşturur
  2. requirements.txt bağımlılıklarını kurar
  3. Playwright için Chromium'u indirir
  4. Veritabanı migration'larını uygular ve yerel sunucuyu başlatır
Sonraki çalıştırmalarda değişmeyen adımlar atlanır (damga dosyaları ile).
Bu dosya yalnızca standart kütüphaneyi kullanır.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
SUPPORTED = ((3, 12), (3, 13))
DEPS_STAMP = VENV / ".zerqon-deps"
CHROMIUM_STAMP = VENV / ".zerqon-chromium"


def _utf8_stdio() -> None:
    """Çıktı dosyaya/boruya yönlendirildiğinde Türkçe karakterler bozulmasın (Windows yerel kod sayfası)."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def log(message: str) -> None:
    print(f"[zerqon] {message}", flush=True)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def interpreter_version(cmd: list[str]) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [*cmd, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        major, minor = out.split(".")
        return int(major), int(minor)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def find_interpreter() -> list[str]:
    if sys.version_info[:2] in SUPPORTED:
        return [sys.executable]
    candidates: list[list[str]] = []
    if os.name == "nt" and shutil.which("py"):
        candidates += [["py", "-3.12"], ["py", "-3.13"]]
    for name in ("python3.12", "python3.13"):
        if shutil.which(name):
            candidates.append([name])
    if shutil.which("uv"):
        for ver in ("3.12", "3.13"):
            try:
                found = subprocess.run(
                    ["uv", "python", "find", ver], capture_output=True, text=True, timeout=30, check=True
                ).stdout.strip()
                if found:
                    candidates.append([found])
            except (OSError, subprocess.SubprocessError):
                pass
    for cmd in candidates:
        if interpreter_version(cmd) in SUPPORTED:
            return cmd
    log(
        "HATA: Python 3.12 (veya 3.13) bulunamadı. Mevcut yorumlayıcı: "
        f"{sys.version.split()[0]}.\n"
        "  Kurulum: https://www.python.org/downloads/  veya  'uv python install 3.12'\n"
        "  Ardından:  py -3.12 run.py  (Windows)  /  python3.12 run.py  (Linux/macOS)"
    )
    sys.exit(1)


def run(cmd: list[str], **kwargs: object) -> None:
    subprocess.run(cmd, check=True, **kwargs)  # type: ignore[arg-type]


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists() and interpreter_version([str(py)]) in SUPPORTED:
        return py
    if VENV.exists():
        log("Mevcut .venv uyumsuz; yeniden oluşturuluyor…")
        shutil.rmtree(VENV)
    interpreter = find_interpreter()
    log(f"Sanal ortam oluşturuluyor ({' '.join(interpreter)})…")
    run([*interpreter, "-m", "venv", str(VENV)])
    return py


def ensure_pip(py: Path) -> None:
    probe = subprocess.run([str(py), "-m", "pip", "--version"], capture_output=True)
    if probe.returncode != 0:
        log("pip kuruluyor…")
        run([str(py), "-m", "ensurepip", "--upgrade"])


def requirements_digest(dev: bool) -> str:
    digest = hashlib.sha256()
    for name in ("requirements.txt", "requirements-dev.txt") if dev else ("requirements.txt",):
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()


def ensure_requirements(py: Path, dev: bool) -> None:
    # Damga biçimi: "<çalışma-zamanı-özeti>|<geliştirme-özeti veya boş>"
    base, full = requirements_digest(False), requirements_digest(True)
    current = DEPS_STAMP.read_text().strip() if DEPS_STAMP.exists() else ""
    if (dev and current == f"{base}|{full}") or (not dev and current.startswith(f"{base}|")):
        return
    ensure_pip(py)
    req = "requirements-dev.txt" if dev else "requirements.txt"
    log(f"Bağımlılıklar kuruluyor ({req})… Bu işlem internet bağlantısı gerektirir.")
    run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / req)])
    DEPS_STAMP.write_text(f"{base}|{full if dev else ''}")


def ensure_chromium(py: Path) -> None:
    version = subprocess.run(
        [str(py), "-c", "import importlib.metadata as m; print(m.version('playwright'))"],
        capture_output=True, text=True,
    ).stdout.strip()
    if CHROMIUM_STAMP.exists() and CHROMIUM_STAMP.read_text().strip() == version:
        return
    log("Playwright Chromium indiriliyor (JavaScript render için)…")
    result = subprocess.run([str(py), "-m", "playwright", "install", "chromium"])
    if result.returncode == 0:
        CHROMIUM_STAMP.write_text(version)
        return
    log(
        "UYARI: Chromium kurulamadı. Standart tarama çalışır; JavaScript/Hibrit mod devre dışı kalır.\n"
        "  Linux'ta sistem bağımlılıkları için:  .venv/bin/python -m playwright install --with-deps chromium"
    )


def main() -> int:
    _utf8_stdio()
    args = sys.argv[1:]
    dev = "--dev" in args
    skip_browser = "--skip-browser-install" in args
    passthrough = [a for a in args if a not in ("--dev", "--skip-browser-install")]

    os.chdir(ROOT)
    py = ensure_venv()
    ensure_requirements(py, dev)
    if not skip_browser:
        ensure_chromium(py)
    try:
        return subprocess.call([str(py), "-m", "zerqon", *passthrough])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
