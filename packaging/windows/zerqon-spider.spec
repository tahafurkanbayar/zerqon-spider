# -*- mode: python ; coding: utf-8 -*-
# Zerqon Spider — Windows tek dosya (.exe) paketi. Doğrudan değil, build.py ile çalıştırın:
#     .venv/Scripts/python packaging/windows/build.py
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

HERE = Path(SPECPATH).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from zerqon import PRODUCT_DESCRIPTION, PRODUCT_NAME, __version__  # noqa: E402

PKG = ROOT / "zerqon"
datas = [
    (str(PKG / "web" / "static"), "zerqon/web/static"),
    (str(PKG / "web" / "templates"), "zerqon/web/templates"),
    (str(PKG / "reports" / "templates"), "zerqon/reports/templates"),
    (str(PKG / "i18n" / "locales"), "zerqon/i18n/locales"),
    (str(PKG / "db" / "migrations"), "zerqon/db/migrations"),
]
# Playwright sürücüsü (node.exe + cli). Chromium pakete gömülmez; ilk kullanımda Ayarlar'dan indirilir.
datas += collect_data_files("playwright")
datas += collect_data_files("webview")

hiddenimports = collect_submodules("zerqon") + collect_submodules("uvicorn")

_ver = tuple(int(x) for x in __version__.split(".")) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver, prodvers=_ver),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Taha Furkan Bayar"),
            StringStruct("FileDescription", f"{PRODUCT_NAME} — {PRODUCT_DESCRIPTION}"),
            StringStruct("FileVersion", __version__),
            StringStruct("InternalName", "ZerqonSpider"),
            StringStruct("OriginalFilename", "ZerqonSpider.exe"),
            StringStruct("ProductName", PRODUCT_NAME),
            StringStruct("ProductVersion", __version__),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "_pytest", "PIL", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ZerqonSpider",
    console=False,
    icon=str(HERE / "zerqon.ico"),
    version=version_info,
    upx=False,
    runtime_tmpdir=None,
)
