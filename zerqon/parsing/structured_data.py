"""Yapılandırılmış veri tespiti: JSON-LD, Microdata, RDFa.

Not: Burada yalnızca sözdizimi ve schema.org türleri için TEMEL alan kontrolleri yapılır.
Google zengin sonuç kurallarının tamamı doğrulanmaz (bkz. README "Bilinen eksikler").
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from lxml import html as lxml_html

# Yaygın türler için temel (asgari) alanlar — tam bir doğrulayıcı değildir.
BASIC_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "Article": ("headline",),
    "NewsArticle": ("headline",),
    "BlogPosting": ("headline",),
    "Product": ("name",),
    "Offer": ("price", "priceCurrency"),
    "AggregateRating": ("ratingValue",),
    "Review": ("itemReviewed", "author"),
    "Organization": ("name",),
    "LocalBusiness": ("name", "address"),
    "Person": ("name",),
    "WebSite": ("url",),
    "WebPage": ("name",),
    "BreadcrumbList": ("itemListElement",),
    "ListItem": ("position",),
    "FAQPage": ("mainEntity",),
    "Question": ("name", "acceptedAnswer"),
    "Event": ("name", "startDate", "location"),
    "Recipe": ("name", "image"),
    "VideoObject": ("name", "thumbnailUrl", "uploadDate"),
    "JobPosting": ("title", "datePosted", "description", "hiringOrganization"),
    "HowTo": ("name", "step"),
    "ImageObject": ("contentUrl",),
}
MAX_JSONLD_BYTES = 512 * 1024
MAX_ITEMS = 200


@dataclass
class StructuredItem:
    format: str  # json-ld | microdata | rdfa
    schema_type: str | None
    valid: bool = True
    error: str | None = None
    missing_fields: list[str] = field(default_factory=list)


def _type_names(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    names: list[str] = []
    for v in values:
        if isinstance(v, str) and v:
            names.append(v.rsplit("/", 1)[-1].rsplit("#", 1)[-1])
    return names


def _check_fields(types: list[str], present: set[str]) -> list[str]:
    missing: list[str] = []
    for t in types:
        for name in BASIC_REQUIRED_FIELDS.get(t, ()):
            if name not in present and name not in missing:
                missing.append(name)
    return missing


def _walk_jsonld(node: Any, out: list[StructuredItem], context_ok: bool, depth: int = 0) -> None:
    if depth > 12 or len(out) >= MAX_ITEMS:
        return
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, out, context_ok, depth + 1)
        return
    if not isinstance(node, dict):
        return
    if "@context" in node:
        context = json.dumps(node["@context"]) if not isinstance(node["@context"], str) else node["@context"]
        context_ok = "schema.org" in context
    if "@graph" in node:
        _walk_jsonld(node["@graph"], out, context_ok, depth + 1)
    if "@type" in node:
        types = _type_names(node["@type"])
        present = {k for k, v in node.items() if v not in (None, "", [], {})}
        item = StructuredItem("json-ld", ",".join(types) or None, missing_fields=_check_fields(types, present))
        if not context_ok:
            item.valid = False
            item.error = "missing_schema_context"
        out.append(item)
        # İç içe öğeleri de listele (Offer, AggregateRating vb.)
        for key, value in node.items():
            if not key.startswith("@") and isinstance(value, (dict, list)):
                _walk_jsonld(value, out, context_ok, depth + 1)


def parse_jsonld(raw: str) -> list[StructuredItem]:
    if len(raw.encode("utf-8", errors="ignore")) > MAX_JSONLD_BYTES:
        return [StructuredItem("json-ld", None, valid=False, error="too_large")]
    text = raw.strip()
    if text.startswith("<!--"):
        text = text[4:]
    if text.endswith("-->"):
        text = text[:-3]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [StructuredItem("json-ld", None, valid=False, error=f"json_syntax: {exc.msg} (satır {exc.lineno}, sütun {exc.colno})")]
    items: list[StructuredItem] = []
    _walk_jsonld(data, items, context_ok=False)
    if not items:
        items.append(StructuredItem("json-ld", None, valid=False, error="no_type"))
    return items


def extract_microdata(root: lxml_html.HtmlElement) -> list[StructuredItem]:
    items: list[StructuredItem] = []
    for scope in root.xpath("//*[@itemscope]"):
        if len(items) >= MAX_ITEMS:
            break
        itemtype = scope.get("itemtype")
        types = _type_names(itemtype.split()) if itemtype else []
        if not types and scope.get("itemprop"):
            continue  # tür bildirmeyen iç içe öğe
        props = {p for el in scope.xpath(".//*[@itemprop]") for p in (el.get("itemprop") or "").split()}
        item = StructuredItem("microdata", ",".join(types) or None, missing_fields=_check_fields(types, props))
        if not types:
            item.valid = False
            item.error = "missing_itemtype"
        items.append(item)
    return items


def extract_rdfa(root: lxml_html.HtmlElement) -> list[StructuredItem]:
    items: list[StructuredItem] = []
    for el in root.xpath("//*[@typeof]"):
        if len(items) >= MAX_ITEMS:
            break
        types = _type_names((el.get("typeof") or "").split())
        props = {p.split(":")[-1] for sub in el.xpath(".//*[@property]") for p in (sub.get("property") or "").split()}
        items.append(StructuredItem("rdfa", ",".join(types) or None, missing_fields=_check_fields(types, props)))
    return items
