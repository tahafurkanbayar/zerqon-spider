"""Windows masaüstü paketini üretir ve doğrular.

    .venv/Scripts/python -m pip install -r requirements-desktop.txt
    .venv/Scripts/python packaging/windows/build.py

Çıktı: `dist/ZerqonSpider-<sürüm>-windows-x64.exe` (+ `.sha256`). Derlemeden sonra paket
`--smoke-test` ile geçici bir veri klasöründe çalıştırılır; başarısızsa çıkış kodu 1'dir.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT))

from zerqon import __version__  # noqa: E402


def build() -> Path:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "pyinstaller"),
         str(HERE / "zerqon-spider.spec")],
        check=True, cwd=ROOT,
    )
    built = DIST / "ZerqonSpider.exe"
    target = DIST / f"ZerqonSpider-{__version__}-windows-x64.exe"
    shutil.copyfile(built, target)
    return target


def smoke_test(exe: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="zerqon-smoke-") as tmp:
        env = {**os.environ, "ZERQON_DATA_DIR": tmp}
        started = time.perf_counter()
        code = subprocess.run([str(exe), "--smoke-test"], env=env, timeout=180).returncode
        elapsed = time.perf_counter() - started
        if code != 0:
            logs = Path(tmp) / "logs"
            for log in logs.glob("*.log"):
                print(log.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise SystemExit(f"Smoke test başarısız (çıkış kodu {code}).")
        print(f"Smoke test başarılı ({elapsed:.1f} sn).")


def write_checksum(exe: Path) -> Path:
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    out = exe.with_name(exe.name + ".sha256")
    out.write_text(f"{digest}  {exe.name}\n", encoding="ascii")
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # CI konsolu cp1252 olabilir; Türkçe çıktı derlemeyi düşürmesin
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.platform != "win32":
        print("Bu betik yalnızca Windows'ta çalışır.")
        return 1
    exe = build()
    smoke_test(exe)
    checksum = write_checksum(exe)
    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"Paket: {exe} ({size_mb:.1f} MB)\nSHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
