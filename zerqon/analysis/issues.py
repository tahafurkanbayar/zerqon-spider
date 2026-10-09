"""SEO sorun tanımları (registry) — bkz. ADR-011.

Her sorunun ad/açıklama/çözüm metni `i18n/locales/*.json` içinde `issues.<code>.{name,desc,fix}` altındadır.
`scope="page"`: tarama sırasında sayfa verisinden üretilir.
`scope="site"`: tarama sonunda tüm veriden üretilir (her sonlandırmada silinip yeniden hesaplanır).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from zerqon.crawler.store import IssueRecord


class Category(StrEnum):
    HTTP = "http"
    URL = "url"
    TITLE = "title"
    DESCRIPTION = "description"
    HEADINGS = "headings"
    CANONICAL = "canonical"
    INDEXABILITY = "indexability"
    IMAGES = "images"
    LINKS = "links"
    CONTENT = "content"
    RENDERING = "rendering"
    STRUCTURED_DATA = "structured_data"
    SOCIAL = "social"
    HREFLANG = "hreflang"
    SITEMAP = "sitemap"
    ROBOTS = "robots"
    MOBILE = "mobile"


SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low", "info")


@dataclass(frozen=True)
class IssueDef:
    code: str
    category: Category
    severity: str
    scope: str = "page"


REGISTRY: dict[str, IssueDef] = {}


def _define(code: str, category: Category, severity: str, scope: str = "page") -> None:
    assert severity in SEVERITIES and scope in ("page", "site"), code
    assert code not in REGISTRY, code
    REGISTRY[code] = IssueDef(code, category, severity, scope)


C = Category
# --- HTTP ---
_define("status_4xx", C.HTTP, "medium")
_define("status_5xx", C.HTTP, "high")
_define("fetch_error", C.HTTP, "high")
_define("blocked_security", C.HTTP, "info")
_define("redirect_temporary", C.HTTP, "low")
_define("meta_refresh_redirect", C.HTTP, "medium")
_define("internal_link_http", C.HTTP, "medium")
_define("mixed_content_image", C.HTTP, "medium")
_define("slow_response", C.HTTP, "low")
_define("body_truncated", C.HTTP, "info")
_define("redirect_chain", C.HTTP, "medium", "site")
_define("redirect_loop", C.HTTP, "high", "site")
_define("redirect_to_error", C.HTTP, "high", "site")
_define("internal_link_to_redirect", C.HTTP, "low", "site")
_define("broken_internal_link", C.HTTP, "high", "site")
_define("http_https_duplicate", C.HTTP, "high", "site")
# --- URL ---
_define("url_too_long", C.URL, "low")
_define("url_parameters", C.URL, "info")
_define("url_uppercase", C.URL, "low")
_define("url_underscores", C.URL, "info")
_define("url_double_slash", C.URL, "low")
_define("url_variant_duplicates", C.URL, "medium", "site")
# --- Title ---
_define("title_missing", C.TITLE, "high")
_define("title_empty", C.TITLE, "high")
_define("title_multiple", C.TITLE, "medium")
_define("title_too_short", C.TITLE, "low")
_define("title_too_long", C.TITLE, "low")
_define("title_h1_mismatch", C.TITLE, "info")
_define("title_duplicate", C.TITLE, "medium", "site")
# --- Description ---
_define("description_missing", C.DESCRIPTION, "medium")
_define("description_empty", C.DESCRIPTION, "medium")
_define("description_multiple", C.DESCRIPTION, "low")
_define("description_too_short", C.DESCRIPTION, "low")
_define("description_too_long", C.DESCRIPTION, "low")
_define("description_duplicate", C.DESCRIPTION, "low", "site")
# --- Headings ---
_define("h1_missing", C.HEADINGS, "medium")
_define("h1_multiple", C.HEADINGS, "low")
_define("heading_empty", C.HEADINGS, "low")
_define("heading_skip_level", C.HEADINGS, "info")
_define("h1_duplicate", C.HEADINGS, "low", "site")
# --- Canonical ---
_define("canonical_multiple", C.CANONICAL, "high")
_define("canonical_invalid", C.CANONICAL, "high")
_define("canonical_in_body", C.CANONICAL, "medium")
_define("canonical_protocol_mismatch", C.CANONICAL, "medium")
_define("canonical_external", C.CANONICAL, "medium")
_define("canonical_relative", C.CANONICAL, "info")
_define("canonical_noindex_conflict", C.CANONICAL, "medium")
_define("canonical_changed_by_js", C.CANONICAL, "medium")
_define("canonical_target_error", C.CANONICAL, "high", "site")
_define("canonical_target_redirect", C.CANONICAL, "medium", "site")
_define("canonical_target_noindex", C.CANONICAL, "high", "site")
_define("canonical_target_canonicalised", C.CANONICAL, "medium", "site")
_define("canonical_missing_on_variant", C.CANONICAL, "low", "site")
# --- Indexability ---
_define("noindex", C.INDEXABILITY, "info")
_define("nofollow_page", C.INDEXABILITY, "info")
_define("blocked_by_robots", C.INDEXABILITY, "info")
_define("robots_changed_by_js", C.INDEXABILITY, "high")
# --- Images ---
_define("image_missing_alt", C.IMAGES, "low")
_define("image_link_missing_alt", C.IMAGES, "medium")
_define("image_missing_dimensions", C.IMAGES, "low")
_define("image_no_lazy_loading", C.IMAGES, "info")
_define("image_broken", C.IMAGES, "medium", "site")
_define("image_too_large", C.IMAGES, "low", "site")
_define("image_legacy_format", C.IMAGES, "info", "site")
_define("image_duplicate_variants", C.IMAGES, "info", "site")
# --- Links ---
_define("no_internal_outlinks", C.LINKS, "low")
_define("too_many_links", C.LINKS, "info")
_define("internal_nofollow", C.LINKS, "info")
_define("empty_anchor", C.LINKS, "low")
_define("deep_page", C.LINKS, "low", "site")
_define("orphan_candidate", C.LINKS, "medium", "site")
# --- Content ---
_define("thin_content", C.CONTENT, "low")
_define("duplicate_content", C.CONTENT, "medium", "site")
_define("near_duplicate_candidate", C.CONTENT, "low", "site")
# --- Rendering ---
_define("content_depends_on_js", C.RENDERING, "info")
_define("title_changed_by_js", C.RENDERING, "low")
_define("links_only_in_rendered_dom", C.RENDERING, "info")
_define("render_failed", C.RENDERING, "medium")
# --- Structured data ---
_define("structured_data_syntax_error", C.STRUCTURED_DATA, "medium")
_define("structured_data_invalid", C.STRUCTURED_DATA, "low")
_define("structured_data_missing_fields", C.STRUCTURED_DATA, "low")
# --- Social ---
_define("og_missing", C.SOCIAL, "low")
_define("og_image_not_absolute", C.SOCIAL, "low")
_define("og_url_mismatch", C.SOCIAL, "info")
_define("twitter_card_missing", C.SOCIAL, "info")
# --- Hreflang ---
_define("html_lang_missing", C.HREFLANG, "low")
_define("hreflang_invalid_code", C.HREFLANG, "medium")
_define("hreflang_missing_self", C.HREFLANG, "low")
_define("hreflang_not_absolute", C.HREFLANG, "low")
_define("hreflang_duplicate_lang", C.HREFLANG, "medium")
_define("hreflang_target_error", C.HREFLANG, "medium", "site")
_define("hreflang_no_return", C.HREFLANG, "medium", "site")
_define("hreflang_target_non_canonical", C.HREFLANG, "medium", "site")
# --- Sitemap / robots ---
_define("robots_unavailable", C.ROBOTS, "high", "site")
_define("robots_missing", C.ROBOTS, "info", "site")
_define("sitemap_missing", C.SITEMAP, "low", "site")
_define("sitemap_invalid", C.SITEMAP, "medium", "site")
_define("sitemap_error", C.SITEMAP, "medium", "site")
_define("sitemap_not_in_robots", C.SITEMAP, "info", "site")
_define("sitemap_url_non_200", C.SITEMAP, "medium", "site")
_define("sitemap_url_noindex", C.SITEMAP, "medium", "site")
_define("sitemap_url_non_canonical", C.SITEMAP, "medium", "site")
_define("sitemap_url_blocked", C.SITEMAP, "medium", "site")
# --- Mobile ---
_define("viewport_missing", C.MOBILE, "low")
del C

SITE_CODES: tuple[str, ...] = tuple(code for code, d in REGISTRY.items() if d.scope == "site")


def issue(code: str, evidence: str | None = None, **signals: Any) -> IssueRecord:
    """Registry'deki tanımdan IssueRecord üretir. Kanıt metni kısaltılır, sinyaller kompakt JSON olur."""
    definition = REGISTRY[code]
    return IssueRecord(
        code=code,
        category=definition.category.value,
        severity=definition.severity,
        evidence=(evidence or "")[:2000] or None,
        signals=json.dumps(signals, ensure_ascii=False, separators=(",", ":"))[:2000] if signals else None,
    )
