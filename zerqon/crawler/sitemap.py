"""XML sitemap ayrıştırma (urlset, sitemapindex, gzip, düz metin).

Güvenlik: harici varlık çözümleme ve ağ erişimi kapalı (XXE), gzip açma boyutu sınırlı (zip bombası).
"""

from __future__ import annotations

import gzip
import io
import zlib
from dataclasses import dataclass, field
from enum import StrEnum

from lxml import etree

MAX_SITEMAP_BYTES = 50 * 1024 * 1024  # sitemaps.org: sıkıştırılmamış en fazla 50 MB
MAX_URLS_PER_SITEMAP = 50_000


class SitemapKind(StrEnum):
    URLSET = "urlset"
    INDEX = "index"
    TEXT = "text"
    INVALID = "invalid"


@dataclass
class SitemapEntry:
    loc: str
    lastmod: str | None = None


@dataclass
class SitemapDocument:
    kind: SitemapKind
    urls: list[SitemapEntry] = field(default_factory=list)
    sitemaps: list[SitemapEntry] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False


def _maybe_decompress(data: bytes) -> bytes:
    if data[:2] != b"\x1f\x8b":
        return data
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = decompressor.decompress(data, MAX_SITEMAP_BYTES + 1)
    if len(out) > MAX_SITEMAP_BYTES:
        raise ValueError("Sıkıştırılmış sitemap izin verilen boyutu aşıyor")
    return out


def _local(tag: object) -> str:
    text = str(tag)
    return text.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_sitemap(data: bytes) -> SitemapDocument:
    try:
        data = _maybe_decompress(data)
    except (OSError, ValueError, zlib.error, EOFError, gzip.BadGzipFile) as exc:
        return SitemapDocument(SitemapKind.INVALID, error=f"gzip: {exc}")

    stripped = data.lstrip()
    if not stripped:
        return SitemapDocument(SitemapKind.INVALID, error="Boş dosya")
    if not stripped.startswith(b"<"):
        return _parse_text(stripped)

    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, huge_tree=False, recover=False, remove_comments=True, load_dtd=False
    )
    try:
        root = etree.parse(io.BytesIO(stripped), parser).getroot()
    except etree.XMLSyntaxError as exc:
        return SitemapDocument(SitemapKind.INVALID, error=f"XML sözdizimi hatası: {exc}")

    root_name = _local(root.tag)
    if root_name == "urlset":
        doc = SitemapDocument(SitemapKind.URLSET)
        child_name, target = "url", doc.urls
    elif root_name == "sitemapindex":
        doc = SitemapDocument(SitemapKind.INDEX)
        child_name, target = "sitemap", doc.sitemaps
    else:
        return SitemapDocument(SitemapKind.INVALID, error=f"Beklenmeyen kök öğe: <{root_name}>")

    for node in root:
        if _local(node.tag) != child_name:
            continue
        loc = lastmod = None
        for child in node:
            name = _local(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()[:40]
        if loc:
            if len(target) >= MAX_URLS_PER_SITEMAP:
                doc.truncated = True
                break
            target.append(SitemapEntry(loc, lastmod))
    return doc


def _parse_text(data: bytes) -> SitemapDocument:
    doc = SitemapDocument(SitemapKind.TEXT)
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(("http://", "https://")):
            if len(doc.urls) >= MAX_URLS_PER_SITEMAP:
                doc.truncated = True
                break
            doc.urls.append(SitemapEntry(line))
    if not doc.urls:
        return SitemapDocument(SitemapKind.INVALID, error="Sitemap XML veya URL listesi değil")
    return doc
