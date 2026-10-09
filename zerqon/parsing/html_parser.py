"""HTML ayrıştırıcı — tek geçişte tüm teknik SEO sinyallerini çıkarır.

Hedef sitelerden gelen HTML güvenilmezdir: hiçbir değer çalıştırılmaz veya ham olarak arayüze basılmaz;
metin alanları uzunluk sınırıyla kesilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree
from lxml import html as lxml_html

from zerqon.crawler.urls import InvalidURLError, normalize_url, resolve_url
from zerqon.parsing.structured_data import StructuredItem, extract_microdata, extract_rdfa, parse_jsonld
from zerqon.parsing.text import collapse_ws, simhash, text_hash, word_count

MAX_TEXT_FIELD = 1000
MAX_ANCHOR = 300
MAX_LINKS = 5000
MAX_IMAGES = 2000
MAX_HEADINGS = 500
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", re.I)
_SPA_ROOT_IDS = ("root", "app", "__next", "__nuxt", "___gatsby", "svelte")
_NON_VISIBLE = ("script", "style", "noscript", "template", "svg", "iframe", "object", "canvas", "head")


@dataclass
class LinkData:
    href: str
    url: str | None
    anchor: str
    rel: str
    nofollow: bool
    kind: str = "a"
    image_only: bool = False


@dataclass
class ImageData:
    src: str
    url: str | None
    alt: str | None
    width: str | None
    height: str | None
    loading: str | None
    has_srcset: bool
    decorative: bool


@dataclass
class ParsedPage:
    base_url: str
    titles: list[str] = field(default_factory=list)
    meta_descriptions: list[str] = field(default_factory=list)
    meta_robots: list[str] = field(default_factory=list)
    canonicals: list[str] = field(default_factory=list)
    canonicals_in_body: int = 0
    headings: list[tuple[int, str]] = field(default_factory=list)
    links: list[LinkData] = field(default_factory=list)
    images: list[ImageData] = field(default_factory=list)
    hreflang: list[tuple[str, str]] = field(default_factory=list)
    structured: list[StructuredItem] = field(default_factory=list)
    lang: str | None = None
    charset: str | None = None
    viewport: str | None = None
    meta_refresh: str | None = None
    meta_refresh_url: str | None = None
    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    text: str = ""
    word_count: int = 0
    text_hash: str | None = None
    simhash: int | None = None
    script_count: int = 0
    spa_root_empty: bool = False
    noscript_text: bool = False
    parse_error: str | None = None

    @property
    def title(self) -> str | None:
        return self.titles[0] if self.titles else None

    @property
    def meta_description(self) -> str | None:
        return self.meta_descriptions[0] if self.meta_descriptions else None

    @property
    def h1s(self) -> list[str]:
        return [text for level, text in self.headings if level == 1]

    @property
    def robots_directives(self) -> set[str]:
        return {d.strip().lower() for value in self.meta_robots for d in value.split(",") if d.strip()}

    def resolved_canonical(self) -> str | None:
        if not self.canonicals:
            return None
        return resolve_url(self.base_url, self.canonicals[0])


def decode_html(body: bytes, content_type: str | None) -> str:
    candidates: list[str] = []
    if content_type and "charset=" in content_type.lower():
        candidates.append(content_type.lower().split("charset=", 1)[1].split(";")[0].strip().strip("\"'"))
    match = _META_CHARSET_RE.search(body[:4096])
    if match:
        candidates.append(match.group(1).decode("ascii", "ignore"))
    candidates.append("utf-8")
    for encoding in candidates:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def _clip(text: str | None, limit: int = MAX_TEXT_FIELD) -> str:
    text = collapse_ws(text)
    return text[:limit]


def _attr(el: lxml_html.HtmlElement, name: str) -> str:
    return (el.get(name) or "").strip()


def parse_html(html_text: str, page_url: str, *, robots_meta_names: tuple[str, ...] = ("robots",)) -> ParsedPage:
    page = ParsedPage(base_url=page_url)
    if not html_text.strip():
        page.parse_error = "empty_document"
        return page
    try:
        root = lxml_html.document_fromstring(html_text)
    except (etree.ParserError, ValueError) as exc:
        page.parse_error = f"parse_error: {exc}"
        return page

    # <base href> bağlantı çözümlemesini etkiler
    base_el = root.find(".//base[@href]")
    if base_el is not None:
        try:
            page.base_url = normalize_url(resolve_url(page_url, base_el.get("href", "")) or page_url)
        except InvalidURLError:
            page.base_url = page_url
    base = page.base_url

    html_el = root if root.tag == "html" else root.find(".//html")
    if html_el is not None:
        page.lang = _attr(html_el, "lang") or None

    for el in root.iter("title"):
        if el.getparent() is not None and el.getparent().tag in ("svg", "symbol"):
            continue
        page.titles.append(_clip(el.text_content()))

    for meta in root.iter("meta"):
        name = _attr(meta, "name").lower()
        prop = _attr(meta, "property").lower()
        content = meta.get("content")
        if meta.get("charset"):
            page.charset = _attr(meta, "charset")
        if name == "description" and content is not None:
            page.meta_descriptions.append(_clip(content))
        elif name in robots_meta_names and content is not None:
            page.meta_robots.append(_clip(content, 300))
        elif name == "viewport":
            page.viewport = _clip(content, 300)
        elif _attr(meta, "http-equiv").lower() == "refresh" and content:
            page.meta_refresh = _clip(content, 500)
            m = re.search(r"url\s*=\s*['\"]?([^'\"]+)", content, re.I)
            if m:
                page.meta_refresh_url = resolve_url(base, m.group(1).strip())
        elif _attr(meta, "http-equiv").lower() == "content-type" and content and "charset=" in content.lower():
            page.charset = content.lower().split("charset=", 1)[1].strip()
        if prop.startswith("og:") and content is not None and prop not in page.og:
            page.og[prop[3:]] = _clip(content)
        if (name.startswith("twitter:") or prop.startswith("twitter:")) and content is not None:
            key = (name or prop)[8:]
            page.twitter.setdefault(key, _clip(content))

    head = root.find(".//head")
    for link in root.iter("link"):
        rels = {r.lower() for r in _attr(link, "rel").split()}
        href = _attr(link, "href")
        if "canonical" in rels:
            in_head = head is not None and any(anc is head for anc in link.iterancestors())
            if in_head:
                page.canonicals.append(href[:2000])
            else:
                page.canonicals_in_body += 1
        if "alternate" in rels and link.get("hreflang"):
            page.hreflang.append((_attr(link, "hreflang")[:35], href[:2000]))

    for el in root.iter("h1", "h2", "h3", "h4", "h5", "h6"):
        if len(page.headings) >= MAX_HEADINGS:
            break
        page.headings.append((int(el.tag[1]), _clip(el.text_content(), 500)))

    for el in root.iter("a", "area"):
        href = el.get("href")
        if href is None or len(page.links) >= MAX_LINKS:
            continue
        rel = _attr(el, "rel").lower()
        anchor = _clip(el.text_content(), MAX_ANCHOR)
        image_only = False
        if not anchor:
            img = el.find(".//img")
            image_only = img is not None
            if img is not None and (img.get("alt") or "").strip():
                anchor = _clip(img.get("alt"), MAX_ANCHOR)
            elif el.get("aria-label"):
                anchor = _clip(el.get("aria-label"), MAX_ANCHOR)
            elif el.get("title"):
                anchor = _clip(el.get("title"), MAX_ANCHOR)
        page.links.append(
            LinkData(
                href=href.strip()[:2000],
                url=resolve_url(base, href),
                anchor=anchor,
                rel=rel[:100],
                nofollow="nofollow" in rel.split(),
                kind=el.tag,
                image_only=image_only,
            )
        )

    for img in root.iter("img"):
        if len(page.images) >= MAX_IMAGES:
            break
        src = _attr(img, "src") or _attr(img, "data-src")
        if not src or src.startswith("data:"):
            continue
        alt = img.get("alt")
        role = _attr(img, "role").lower()
        decorative = (alt is not None and alt.strip() == "") or role in ("presentation", "none") or _attr(
            img, "aria-hidden"
        ).lower() == "true"
        page.images.append(
            ImageData(
                src=src[:2000],
                url=resolve_url(base, src),
                alt=_clip(alt, 500) if alt is not None else None,
                width=_attr(img, "width")[:20] or None,
                height=_attr(img, "height")[:20] or None,
                loading=_attr(img, "loading").lower()[:20] or None,
                has_srcset=bool(img.get("srcset") or img.get("data-srcset")),
                decorative=decorative,
            )
        )

    for script in root.iter("script"):
        page.script_count += 1
        if _attr(script, "type").lower() == "application/ld+json" and script.text:
            page.structured.extend(parse_jsonld(script.text))
    try:
        page.structured.extend(extract_microdata(root))
        page.structured.extend(extract_rdfa(root))
    except etree.XPathError:
        pass

    body = root.find(".//body")
    if body is not None:
        for spa_id in _SPA_ROOT_IDS:
            el = body.find(f".//*[@id='{spa_id}']")
            if el is not None and not collapse_ws(el.text_content()) and len(el) <= 1:
                page.spa_root_empty = True
                break
        page.noscript_text = any(collapse_ws(n.text_content()) for n in body.iter("noscript"))
        etree.strip_elements(body, *_NON_VISIBLE, with_tail=False)
        page.text = collapse_ws(body.text_content())
    page.word_count = word_count(page.text)
    page.text_hash = text_hash(page.text)
    page.simhash = simhash(page.text)
    return page
