"""Sayfa kontrolleri, indexability ve önceliklendirme birim testleri."""

from __future__ import annotations

import pytest

from zerqon.analysis.context import PageContext
from zerqon.analysis.indexability import IndexSignals, evaluate, parse_directives
from zerqon.analysis.issues import REGISTRY
from zerqon.analysis.lang_codes import is_valid_hreflang
from zerqon.analysis.prioritization import shift
from zerqon.analysis.runner import PageAnalysisRunner
from zerqon.crawler.fetcher import FetchResult
from zerqon.crawler.scope import CrawlScope
from zerqon.i18n import SUPPORTED_LANGUAGES, load_catalog
from zerqon.parsing.html_parser import parse_html
from zerqon.schemas import CrawlSettingsModel

URL = "https://example.com/page"
RUNNER = PageAnalysisRunner()


def analyze(html: str, *, url: str = URL, status: int = 200, x_robots: str = "", **settings: object) -> set[str]:
    fetch = FetchResult(url=url, status_code=status, content_type="text/html; charset=utf-8", elapsed_ms=50)
    ctx = PageContext(
        url=url, key=url, depth=0, fetch=fetch, raw=parse_html(html, url), rendered=None,
        settings=CrawlSettingsModel(**settings), scope=CrawlScope("https://example.com/"), x_robots_tag=x_robots,
    )
    return {i.code for i in RUNNER.analyze_page(ctx)}


GOOD_HEAD = (
    '<html lang="tr"><head><title>Teknik SEO denetimi rehberi ve kontrol listesi</title>'
    '<meta name="description" content="Teknik SEO denetimi için adım adım rehber: tarama, indeksleme, canonical ve daha fazlası burada.">'
    '<meta name="viewport" content="width=device-width">'
    f'<link rel="canonical" href="{URL}">'
    '<meta property="og:title" content="x"><meta property="og:description" content="x">'
    '<meta property="og:image" content="https://example.com/i.png"><meta property="og:url" content="https://example.com/page">'
    '<meta name="twitter:card" content="summary"></head>'
)


def body(inner: str) -> str:
    return f"<body>{inner}<a href='/other'>Diğer sayfa</a></body></html>"


def test_clean_page_has_no_meta_issues() -> None:
    codes = analyze(GOOD_HEAD + body("<h1>Teknik SEO denetimi</h1>" + "<p>kelime </p>" * 250))
    assert not codes & {"title_missing", "description_missing", "h1_missing", "canonical_invalid", "og_missing"}
    assert "thin_content" not in codes


# ------------------------------------------------------------------ Title / description
@pytest.mark.parametrize(
    ("head", "expected"),
    [
        ("<head></head>", "title_missing"),
        ("<head><title></title></head>", "title_empty"),
        ("<head><title>Kısa</title></head>", "title_too_short"),
        ("<head><title>" + "Uzun başlık " * 10 + "</title></head>", "title_too_long"),
        ("<head><title>Bir başlık örneği yeterli uzunlukta</title><title>İkinci</title></head>", "title_multiple"),
    ],
)
def test_title_checks(head: str, expected: str) -> None:
    assert expected in analyze(f"<html>{head}{body('<h1>x</h1>')}")


def test_title_thresholds_are_configurable() -> None:
    html = "<html><head><title>Orta uzunlukta başlık</title></head>" + body("")
    assert "title_too_short" in analyze(html)
    assert "title_too_short" not in analyze(html, title_min_chars=10)


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        ("<head><title>t</title></head>", "description_missing"),
        ('<head><meta name="description" content=""></head>', "description_empty"),
        ('<head><meta name="description" content="kısa"></head>', "description_too_short"),
        ('<head><meta name="description" content="' + "a" * 200 + '"></head>', "description_too_long"),
        ('<head><meta name="description" content="' + "a" * 80 + '"><meta name="description" content="b"></head>', "description_multiple"),
    ],
)
def test_description_checks(head: str, expected: str) -> None:
    assert expected in analyze(f"<html>{head}{body('')}")


# ------------------------------------------------------------------ Headings
def test_heading_checks() -> None:
    assert "h1_missing" in analyze(GOOD_HEAD + body("<h2>Alt</h2>"))
    assert "h1_multiple" in analyze(GOOD_HEAD + body("<h1>A</h1><h1>B</h1>"))
    assert "heading_empty" in analyze(GOOD_HEAD + body("<h1>A</h1><h2></h2>"))
    assert "heading_skip_level" in analyze(GOOD_HEAD + body("<h1>A</h1><h3>C</h3>"))
    assert "heading_skip_level" not in analyze(GOOD_HEAD + body("<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2>"))
    assert "title_h1_mismatch" in analyze(GOOD_HEAD + body("<h1>Kedi maması fiyatları</h1>"))


# ------------------------------------------------------------------ Canonical
def test_canonical_checks() -> None:
    def head(extra: str) -> str:
        return f"<html><head><title>Başlık yeterince uzun bir başlık</title>{extra}</head>"

    assert "canonical_multiple" in analyze(
        head('<link rel="canonical" href="/a"><link rel="canonical" href="/b">') + body("")
    )
    assert "canonical_invalid" in analyze(head('<link rel="canonical" href="">') + body(""))
    assert "canonical_external" in analyze(head('<link rel="canonical" href="https://other.example/x">') + body(""))
    assert "canonical_relative" in analyze(head('<link rel="canonical" href="/page">') + body(""))
    assert "canonical_protocol_mismatch" in analyze(head('<link rel="canonical" href="http://example.com/page">') + body(""))
    assert "canonical_in_body" in analyze(head("") + body('<link rel="canonical" href="/x">'))
    assert "canonical_noindex_conflict" in analyze(
        head('<meta name="robots" content="noindex"><link rel="canonical" href="https://example.com/other">') + body("")
    )
    # Canonical eksikliği tek başına sorun değildir
    codes = analyze(head("") + body(""))
    assert not {c for c in codes if c.startswith("canonical")}


# ------------------------------------------------------------------ Indexability
@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (IndexSignals("u", "ok", 200), ("indexable", None)),
        (IndexSignals("u", "blocked_robots", None), ("non_indexable", "blocked_robots")),
        (IndexSignals("u", "error", None), ("non_indexable", "fetch_error")),
        (IndexSignals("u", "ok", 301), ("non_indexable", "redirect")),
        (IndexSignals("u", "ok", 404), ("non_indexable", "client_error")),
        (IndexSignals("u", "ok", 503), ("non_indexable", "server_error")),
        (IndexSignals("u", "ok", 200, meta_robots="noindex, follow"), ("non_indexable", "noindex")),
        (IndexSignals("u", "ok", 200, x_robots_tag="none"), ("non_indexable", "noindex")),
        (IndexSignals("u", "ok", 200, canonical_key="other"), ("non_indexable", "canonicalised")),
        (IndexSignals("u", "ok", 200, canonical_key="u"), ("indexable", None)),
        (IndexSignals("u", "ok", 200, meta_robots="nofollow"), ("indexable", None)),
    ],
)
def test_indexability(signals: IndexSignals, expected: tuple[str, str | None]) -> None:
    assert evaluate(signals) == expected


def test_directive_parsing() -> None:
    assert parse_directives("NOINDEX, Follow", None) == {"noindex", "follow"}
    assert {"noindex", "nofollow"} <= parse_directives(None, "none")


def test_noindex_and_xrobots_issue() -> None:
    assert "noindex" in analyze(GOOD_HEAD + body(""), x_robots="noindex")
    assert "nofollow_page" in analyze(GOOD_HEAD.replace("</head>", '<meta name="robots" content="nofollow"></head>') + body(""))


# ------------------------------------------------------------------ Diğer
def test_images_links_content_social() -> None:
    codes = analyze(
        GOOD_HEAD + body('<h1>x</h1><img src="/a.png"><img src="/b.png" alt=""><a href="/x"><img src="/c.png"></a>')
    )
    assert {"image_missing_alt", "image_link_missing_alt", "image_missing_dimensions", "thin_content"} <= codes
    assert "og_missing" in analyze("<html><head><title>t</title></head>" + body(""))
    assert "no_internal_outlinks" in analyze("<html><head><title>t</title></head><body><p>x</p></body></html>")


def test_structured_data_checks() -> None:
    html = GOOD_HEAD.replace(
        "</head>",
        '<script type="application/ld+json">{bad json}</script>'
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product"}</script></head>',
    )
    codes = analyze(html + body(""))
    assert {"structured_data_syntax_error", "structured_data_missing_fields"} <= codes


def test_hreflang_checks() -> None:
    html = GOOD_HEAD.replace(
        "</head>",
        '<link rel="alternate" hreflang="en-uk" href="https://example.com/en">'
        '<link rel="alternate" hreflang="tr" href="/tr"></head>',
    )
    codes = analyze(html + body(""))
    assert {"hreflang_invalid_code", "hreflang_not_absolute", "hreflang_missing_self"} <= codes


@pytest.mark.parametrize("code", ["tr", "tr-TR", "en-GB", "zh-Hant-TW", "es-419", "x-default", "se", "ar"])
def test_valid_hreflang(code: str) -> None:
    assert is_valid_hreflang(code)


@pytest.mark.parametrize("code", ["en-uk", "jp", "english", "en_US", "tr-TUR", ""])
def test_invalid_hreflang(code: str) -> None:
    assert not is_valid_hreflang(code)


def test_http_status_issues() -> None:
    assert "status_4xx" in analyze("", status=404)
    assert "status_5xx" in analyze("", status=503)


def test_severity_shift_bounds() -> None:
    assert shift("critical", -1) == "critical"
    assert shift("info", 1) == "info"
    assert shift("low", -1) == "medium"


def test_every_issue_has_translations() -> None:
    for lang in SUPPORTED_LANGUAGES:
        catalog = load_catalog(lang)
        for code in REGISTRY:
            for part in ("name", "desc", "fix"):
                assert f"issues.{code}.{part}" in catalog, f"{lang}: issues.{code}.{part}"
