"""Sürüm tutarlılığı: paket, pyproject.toml ve CHANGELOG aynı sürümü göstermeli."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from zerqon import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_pyproject_matches_package_version() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_changelog_has_entry_for_current_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(__version__)}\] — \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE)
    link = re.search(rf"^\[{re.escape(__version__)}\]: (\S+)$", changelog, re.MULTILINE)
    assert link and link.group(1).startswith("https://github.com/tahafurkanbayar/zerqon-spider/")
    assert link.group(1).endswith(f"v{__version__}")
