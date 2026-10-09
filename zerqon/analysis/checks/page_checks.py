"""Sayfa düzeyi kontroller (tarama sırasında, tek sayfanın verisiyle).

Eşikler `CrawlSettingsModel` üzerinden yapılandırılabilir; bunlar öneri değerleridir, arama motoru kuralı değildir.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urlsplit

from zerqon.analysis.context import PageContext
from zerqon.analysis.indexability import parse_directives
from zerqon.analysis.issues import issue
from zerqon.analysis.registry import page_check
from zerqon.analysis.lang_codes import is_valid_hreflang
from zerqon.crawler.store import IssueRecord
from zerqon.crawler.urls import resolve_url, url_key
from zerqon.parsing.text import words

SLOW_RESPONSE_MS = 2000
TOO_MANY_LINKS = 300
LAZY_MIN_IMAGES = 6
TEMPORARY_REDIRECTS = frozenset({302, 303, 307})


def _sample(values: list[str], limit: int = 5) -> str:
    shown = values[:limit]
    more = len(values) - len(shown)
    return "\n".join(shown) + (f"\n… (+{more})" if more > 0 else "")


# ----------------------------------------------------------------------------- HTTP & URL
@page_check
def check_http(ctx: PageContext) -> Iterator[IssueRecord]:
    fetch = ctx.fetch
    if fetch.error_code == "blocked_security":
        yield issue("blocked_security", fetch.error_detail, reason=fetch.error_detail)
        return
    if fetch.error_code:
        yield issue("fetch_error", f"{fetch.error_code}: {fetch.error_detail or ''}", error=fetch.error_code)
        return
    status = fetch.status_code or 0
    if 400 <= status < 500:
        yield issue("status_4xx", f"HTTP {status}", status=status)
    elif status >= 500:
        yield issue("status_5xx", f"HTTP {status}", status=status)
    elif status in TEMPORARY_REDIRECTS and fetch.is_redirect:
        yield issue("redirect_temporary", f"HTTP {status} → {fetch.headers.get('location', '')}", status=status)
    if fetch.elapsed_ms and fetch.elapsed_ms > SLOW_RESPONSE_MS:
        yield issue("slow_response", f"{fetch.elapsed_ms} ms", response_ms=fetch.elapsed_ms, threshold=SLOW_RESPONSE_MS)
    if fetch.truncated:
        yield issue("body_truncated", f"{len(fetch.body)} bayt okundu", bytes=len(fetch.body))


@page_check
def check_url_format(ctx: PageContext) -> Iterator[IssueRecord]:
    parts = urlsplit(ctx.url)
    if len(ctx.url) > ctx.settings.max_url_length:
        yield issue("url_too_long", f"{len(ctx.url)} karakter", length=len(ctx.url), threshold=ctx.settings.max_url_length)
    if parts.query:
        yield issue("url_parameters", parts.query[:300], params=len(parts.query.split("&")))
    if any(ch.isupper() for ch in parts.path):
        yield issue("url_uppercase", parts.path[:300])
    if "_" in parts.path:
        yield issue("url_underscores", parts.path[:300])
    if "//" in parts.path:
        yield issue("url_double_slash", parts.path[:300])


# ----------------------------------------------------------------------------- Title / description / headings
@page_check
def check_title(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    s = ctx.settings
    if not page.titles:
        yield issue("title_missing")
        return
    title = page.titles[0]
    if len(page.titles) > 1:
        yield issue("title_multiple", _sample(page.titles), count=len(page.titles))
    if not title:
        yield issue("title_empty")
        return
    if len(title) < s.title_min_chars:
        yield issue("title_too_short", f"{title} ({len(title)})", length=len(title), min=s.title_min_chars)
    elif len(title) > s.title_max_chars:
        yield issue("title_too_long", f"{title} ({len(title)})", length=len(title), max=s.title_max_chars)
    h1s = [h for h in page.h1s if h]
    if h1s:
        title_words = {w.casefold() for w in words(title) if len(w) > 2}
        h1_words = {w.casefold() for w in words(h1s[0]) if len(w) > 2}
        if title_words and h1_words and not (title_words & h1_words):
            yield issue("title_h1_mismatch", f"title: {title}\nh1: {h1s[0]}")


@page_check
def check_description(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    s = ctx.settings
    if not page.meta_descriptions:
        yield issue("description_missing")
        return
    desc = page.meta_descriptions[0]
    if len(page.meta_descriptions) > 1:
        yield issue("description_multiple", _sample(page.meta_descriptions), count=len(page.meta_descriptions))
    if not desc:
        yield issue("description_empty")
    elif len(desc) < s.description_min_chars:
        yield issue("description_too_short", f"{desc} ({len(desc)})", length=len(desc), min=s.description_min_chars)
    elif len(desc) > s.description_max_chars:
        yield issue("description_too_long", f"{desc[:200]}… ({len(desc)})", length=len(desc), max=s.description_max_chars)


@page_check
def check_headings(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    h1s = page.h1s
    if not h1s:
        yield issue("h1_missing")
    elif len(h1s) > 1:
        yield issue("h1_multiple", _sample(h1s), count=len(h1s))
    empty = [f"H{level}" for level, text in page.headings if not text]
    if empty:
        yield issue("heading_empty", ", ".join(empty[:10]), count=len(empty))
    skips: list[str] = []
    previous = 0
    for level, text in page.headings:
        if previous and level > previous + 1:
            skips.append(f"H{previous} → H{level}: {text[:60]}")
        previous = level
    if skips:
        yield issue("heading_skip_level", _sample(skips), count=len(skips))


# ----------------------------------------------------------------------------- Canonical & indexability sinyalleri
@page_check
def check_canonical(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    if len(page.canonicals) > 1:
        distinct = sorted(set(page.canonicals))
        yield issue("canonical_multiple", _sample(distinct), count=len(page.canonicals), distinct=len(distinct))
    if page.canonicals_in_body:
        yield issue("canonical_in_body", f"{page.canonicals_in_body}", count=page.canonicals_in_body)
    if not page.canonicals:
        return
    raw_href = page.canonicals[0]
    target = page.resolved_canonical()
    if not raw_href or target is None:
        yield issue("canonical_invalid", raw_href or "(boş)")
        return
    if not raw_href.lower().startswith(("http://", "https://")):
        yield issue("canonical_relative", raw_href)
    target_parts = urlsplit(target)
    if target_parts.scheme != ctx.scheme and url_key(target.replace("http://", "https://", 1)) == url_key(
        ctx.url.replace("http://", "https://", 1)
    ):
        yield issue("canonical_protocol_mismatch", f"{ctx.url} → {target}", page=ctx.scheme, canonical=target_parts.scheme)
    elif target_parts.scheme == "http" and ctx.scheme == "https":
        yield issue("canonical_protocol_mismatch", f"{ctx.url} → {target}", page=ctx.scheme, canonical="http")
    if not ctx.scope.is_internal(target):
        yield issue("canonical_external", target)
    directives = parse_directives(", ".join(page.meta_robots), ctx.x_robots_tag)
    if "noindex" in directives and url_key(target) != ctx.key:
        yield issue("canonical_noindex_conflict", f"noindex + canonical → {target}")
    if ctx.rendered is not None and ctx.raw is not None:
        raw_c, ren_c = ctx.raw.resolved_canonical(), ctx.rendered.resolved_canonical()
        if raw_c != ren_c:
            yield issue("canonical_changed_by_js", f"ham: {raw_c or '—'}\nrender: {ren_c or '—'}")


@page_check
def check_robots_directives(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    status = ctx.fetch.status_code or 0
    if ctx.fetch.error_code or not 200 <= status < 300:
        return
    meta = ", ".join(page.meta_robots) if page else ""
    directives = parse_directives(meta, ctx.x_robots_tag)
    sources = [s for s, v in (("meta", meta), ("x-robots-tag", ctx.x_robots_tag)) if "noindex" in parse_directives(v)]
    if "noindex" in directives:
        yield issue("noindex", f"meta robots: {meta or '—'}\nX-Robots-Tag: {ctx.x_robots_tag or '—'}", sources=sources)
    if "nofollow" in directives:
        yield issue("nofollow_page", f"meta robots: {meta or '—'}\nX-Robots-Tag: {ctx.x_robots_tag or '—'}")
    if ctx.rendered is not None and ctx.raw is not None:
        raw_d = parse_directives(", ".join(ctx.raw.meta_robots))
        ren_d = parse_directives(", ".join(ctx.rendered.meta_robots))
        if ("noindex" in raw_d) != ("noindex" in ren_d) or ("nofollow" in raw_d) != ("nofollow" in ren_d):
            yield issue(
                "robots_changed_by_js",
                f"ham: {', '.join(ctx.raw.meta_robots) or '—'}\nrender: {', '.join(ctx.rendered.meta_robots) or '—'}",
            )
    if ctx.effective is not None and ctx.effective.meta_refresh_url:
        yield issue("meta_refresh_redirect", ctx.effective.meta_refresh or "", target=ctx.effective.meta_refresh_url)


# ----------------------------------------------------------------------------- Görseller ve bağlantılar
@page_check
def check_images(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None or not page.images:
        return
    missing_alt = [img.url or img.src for img in page.images if img.alt is None and not img.decorative]
    if missing_alt:
        yield issue("image_missing_alt", _sample(missing_alt), count=len(missing_alt))
    # Bağlantının tek içeriği alt metni olmayan bir görselse bağlantının erişilebilir adı/anchor'u boş kalır
    linked_no_alt = [link.url or link.href for link in page.links if link.image_only and not link.anchor]
    if linked_no_alt:
        yield issue("image_link_missing_alt", _sample(linked_no_alt), count=len(linked_no_alt))
    no_dims = [img.url or img.src for img in page.images if not (img.width and img.height)]
    if no_dims:
        yield issue("image_missing_dimensions", _sample(no_dims), count=len(no_dims))
    if len(page.images) >= LAZY_MIN_IMAGES and not any(img.loading == "lazy" for img in page.images):
        yield issue("image_no_lazy_loading", f"{len(page.images)} görsel", count=len(page.images))
    if ctx.scheme == "https":
        insecure = [img.url for img in page.images if img.url and img.url.startswith("http://")]
        if insecure:
            yield issue("mixed_content_image", _sample(insecure), count=len(insecure))


@page_check
def check_links(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    internal = [link for link in page.links if link.url and ctx.scope.is_internal(link.url)]
    if not internal:
        yield issue("no_internal_outlinks")
    if len(page.links) > TOO_MANY_LINKS:
        yield issue("too_many_links", f"{len(page.links)}", count=len(page.links), threshold=TOO_MANY_LINKS)
    nofollow = [link.url or link.href for link in internal if link.nofollow]
    if nofollow:
        yield issue("internal_nofollow", _sample(nofollow), count=len(nofollow))
    empty = [link.url or link.href for link in internal if not link.anchor and not link.image_only]
    if empty:
        yield issue("empty_anchor", _sample(empty), count=len(empty))
    if ctx.scheme == "https":
        insecure = sorted({link.url for link in internal if link.url and link.url.startswith("http://")})
        if insecure:
            yield issue("internal_link_http", _sample(insecure), count=len(insecure))


# ----------------------------------------------------------------------------- İçerik ve render
@page_check
def check_content(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    if page.word_count < ctx.settings.min_word_count:
        yield issue("thin_content", f"{page.word_count} kelime", words=page.word_count, min=ctx.settings.min_word_count)
    if not page.viewport:
        yield issue("viewport_missing")


@page_check
def check_rendering(ctx: PageContext) -> Iterator[IssueRecord]:
    if ctx.render_error:
        yield issue("render_failed", ctx.render_error)
    if ctx.rendered is None or ctx.raw is None:
        return
    raw, ren = ctx.raw, ctx.rendered
    if ren.word_count > raw.word_count * 1.5 + 50:
        yield issue(
            "content_depends_on_js",
            f"ham: {raw.word_count} kelime\nrender: {ren.word_count} kelime",
            raw_words=raw.word_count,
            rendered_words=ren.word_count,
        )
    if (raw.title or "") != (ren.title or ""):
        yield issue("title_changed_by_js", f"ham: {raw.title or '—'}\nrender: {ren.title or '—'}")
    raw_targets = {link.url for link in raw.links if link.url}
    render_only = sorted({link.url for link in ren.links if link.url and link.url not in raw_targets})
    if render_only:
        yield issue("links_only_in_rendered_dom", _sample(render_only), count=len(render_only))


# ----------------------------------------------------------------------------- Yapılandırılmış veri ve sosyal
@page_check
def check_structured_data(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    syntax = [s.error for s in page.structured if s.error and s.error.startswith("json_syntax")]
    if syntax:
        yield issue("structured_data_syntax_error", _sample([e or "" for e in syntax]), count=len(syntax))
    invalid = [f"{s.format}: {s.error}" for s in page.structured if s.error and not s.error.startswith("json_syntax")]
    if invalid:
        yield issue("structured_data_invalid", _sample(invalid), count=len(invalid))
    missing = [f"{s.schema_type}: {', '.join(s.missing_fields)}" for s in page.structured if s.missing_fields]
    if missing:
        yield issue("structured_data_missing_fields", _sample(missing), count=len(missing))


@page_check
def check_social(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    missing = [f"og:{key}" for key in ("title", "description", "image", "url") if not page.og.get(key)]
    if missing:
        yield issue("og_missing", ", ".join(missing), missing=missing)
    image = page.og.get("image")
    if image and not image.lower().startswith(("http://", "https://")):
        yield issue("og_image_not_absolute", image)
    og_url = page.og.get("url")
    canonical = page.resolved_canonical() or ctx.url
    if og_url:
        resolved = resolve_url(ctx.url, og_url)
        if resolved and url_key(resolved) != url_key(canonical):
            yield issue("og_url_mismatch", f"og:url: {og_url}\ncanonical: {canonical}")
    if not page.twitter.get("card"):
        yield issue("twitter_card_missing")


# ----------------------------------------------------------------------------- Çok dilli
@page_check
def check_hreflang(ctx: PageContext) -> Iterator[IssueRecord]:
    page = ctx.effective
    if not ctx.is_html_ok or page is None:
        return
    if not page.lang:
        yield issue("html_lang_missing")
    if not page.hreflang:
        return
    invalid = [code for code, _ in page.hreflang if not is_valid_hreflang(code)]
    if invalid:
        yield issue("hreflang_invalid_code", ", ".join(invalid[:20]), codes=invalid[:20])
    relative = [href for _, href in page.hreflang if not re.match(r"^https?://", href, re.I)]
    if relative:
        yield issue("hreflang_not_absolute", _sample(relative), count=len(relative))
    targets = {url_key(resolve_url(page.base_url, href) or href) for _, href in page.hreflang}
    own = url_key(page.resolved_canonical() or ctx.url)
    if ctx.key not in targets and own not in targets:
        yield issue("hreflang_missing_self", f"{len(page.hreflang)} hreflang")
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for code, href in page.hreflang:
        norm = code.lower()
        if norm in seen and url_key(seen[norm]) != url_key(href):
            duplicates.append(f"{code}: {seen[norm]} / {href}")
        seen.setdefault(norm, href)
    if duplicates:
        yield issue("hreflang_duplicate_lang", _sample(duplicates), count=len(duplicates))
