from __future__ import annotations

import re
from pathlib import Path

from zerqon.i18n import SUPPORTED_LANGUAGES, Translator, load_catalog

TEMPLATES = Path(__file__).resolve().parent.parent / "zerqon" / "web" / "templates"


def test_locales_have_identical_keys() -> None:
    catalogs = {lang: set(load_catalog(lang)) for lang in SUPPORTED_LANGUAGES}
    reference = catalogs["tr"]
    for lang, keys in catalogs.items():
        assert keys == reference, f"{lang}: eksik={reference - keys} fazla={keys - reference}"


def test_static_template_keys_exist() -> None:
    """Şablonlarda sabit yazılmış t('...') anahtarlarının hepsi katalogda olmalı."""
    catalog = load_catalog("tr")
    pattern = re.compile(r"""\bt\(\s*['"]([a-z0-9_.]+)['"]""")
    missing: set[str] = set()
    for path in TEMPLATES.rglob("*.html"):
        for key in pattern.findall(path.read_text(encoding="utf-8")):
            if key.endswith((".", "_")):
                continue  # dinamik anahtar öneki
            if key not in catalog:
                missing.add(f"{path.name}:{key}")
    assert not missing, sorted(missing)


def test_translator_fallback_and_format() -> None:
    t = Translator("en")
    assert t("nav.dashboard") == "Dashboard"
    assert Translator("tr")("nav.dashboard") == "Kontrol Paneli"
    assert t("does.not.exist") == "does.not.exist"
    assert t("crawl.crawled_n", n=5) == "5 URLs crawled"
    assert Translator("xx").language == "tr"
