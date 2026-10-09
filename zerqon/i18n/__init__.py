"""Merkezi çeviri altyapısı.

Metinler `locales/<dil>.json` dosyalarında iç içe sözlükler olarak tutulur ve
nokta ile ayrılmış anahtarlarla erişilir: `t("nav.dashboard")`.
Eksik anahtar önce varsayılan dile (tr), sonra anahtarın kendisine düşer.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).parent / "locales"
SUPPORTED_LANGUAGES: tuple[str, ...] = ("tr", "en")
DEFAULT_LANGUAGE = "tr"


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, full))
        else:
            flat[full] = str(value)
    return flat


@lru_cache(maxsize=None)
def load_catalog(language: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{language}.json"
    with path.open(encoding="utf-8") as fh:
        return _flatten(json.load(fh))


def normalize_language(language: str | None) -> str:
    if language and language.lower()[:2] in SUPPORTED_LANGUAGES:
        return language.lower()[:2]
    return DEFAULT_LANGUAGE


class Translator:
    def __init__(self, language: str | None = None) -> None:
        self.language = normalize_language(language)
        self._catalog = load_catalog(self.language)
        self._fallback = load_catalog(DEFAULT_LANGUAGE)

    def has(self, key: str) -> bool:
        return key in self._catalog or key in self._fallback

    def __call__(self, key: str, default: str | None = None, **kwargs: Any) -> str:
        text = self._catalog.get(key) or self._fallback.get(key)
        if text is None:
            text = default if default is not None else key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text


def get_translator(language: str | None = None) -> Translator:
    return Translator(language)
