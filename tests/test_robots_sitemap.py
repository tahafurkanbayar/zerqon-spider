from __future__ import annotations

import gzip

from zerqon.crawler.robots import RobotsStatus, RobotsTxt
from zerqon.crawler.sitemap import SitemapKind, parse_sitemap

UA = "Mozilla/5.0 (compatible; ZerqonSpider/1.0.0; +https://github.com/x/y)"

ROBOTS = """
# yorum
User-agent: *
Disallow: /private/
Disallow: /*.pdf$
Disallow: /search
Allow: /search/about
Crawl-delay: 2

User-agent: ZerqonSpider
Disallow: /no-zerqon/

User-agent: Googlebot
Disallow: /

Sitemap: https://example.com/sitemap.xml
"""


def test_specific_group_overrides_wildcard() -> None:
    robots = RobotsTxt.parse(ROBOTS)
    # ZerqonSpider grubu eşleşir → yalnızca o grubun kuralları geçerli
    assert not robots.is_allowed("https://example.com/no-zerqon/a", UA)
    assert robots.is_allowed("https://example.com/private/a", UA)
    generic = "SomeOtherBot/2.0"
    assert not robots.is_allowed("https://example.com/private/a", generic)
    assert not robots.is_allowed("https://example.com/", "Googlebot/2.1")
    assert robots.sitemaps == ["https://example.com/sitemap.xml"]


def test_wildcards_longest_match_and_allow_tie() -> None:
    robots = RobotsTxt.parse(ROBOTS)
    ua = "OtherBot"
    assert not robots.is_allowed("https://example.com/files/doc.pdf", ua)
    assert robots.is_allowed("https://example.com/files/doc.pdf?x=1", ua)  # $ sonu
    assert not robots.is_allowed("https://example.com/search?q=1", ua)
    assert robots.is_allowed("https://example.com/search/about", ua)  # daha uzun Allow kazanır
    assert robots.is_allowed("https://example.com/robots.txt", ua)
    assert robots.crawl_delay(ua) == 2.0

    tie = RobotsTxt.parse("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert tie.is_allowed("https://example.com/page", ua)


def test_empty_disallow_and_status_policies() -> None:
    assert RobotsTxt.parse("User-agent: *\nDisallow:\n").is_allowed("https://e.com/x", UA)
    assert RobotsTxt.allow_all().is_allowed("https://e.com/x", UA)
    blocked = RobotsTxt.disallow_all()
    assert blocked.status is RobotsStatus.UNAVAILABLE
    assert not blocked.is_allowed("https://e.com/x", UA)


def test_percent_encoding_match() -> None:
    robots = RobotsTxt.parse("User-agent: *\nDisallow: /ürün/\n")
    assert not robots.is_allowed("https://e.com/%C3%BCr%C3%BCn/1", "bot")


URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc> https://example.com/a </loc><lastmod>2026-01-01</lastmod></url>
<url><loc>https://example.com/b</loc></url>
</urlset>"""


def test_parse_urlset_and_gzip() -> None:
    doc = parse_sitemap(URLSET)
    assert doc.kind is SitemapKind.URLSET
    assert [e.loc for e in doc.urls] == ["https://example.com/a", "https://example.com/b"]
    assert doc.urls[0].lastmod == "2026-01-01"
    assert parse_sitemap(gzip.compress(URLSET)).kind is SitemapKind.URLSET


def test_parse_index_text_and_invalid() -> None:
    index = b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://e.com/s1.xml</loc></sitemap></sitemapindex>'
    doc = parse_sitemap(index)
    assert doc.kind is SitemapKind.INDEX and doc.sitemaps[0].loc == "https://e.com/s1.xml"
    assert parse_sitemap(b"https://e.com/1\nhttps://e.com/2\n").kind is SitemapKind.TEXT
    bad = parse_sitemap(b"<urlset><url><loc>x</url></urlset>")
    assert bad.kind is SitemapKind.INVALID and bad.error
    assert parse_sitemap(b"<html></html>").kind is SitemapKind.INVALID


def test_sitemap_xxe_not_resolved(tmp_path) -> None:  # type: ignore[no-untyped-def]
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    payload = (
        f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///{secret.as_posix()}">]>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://e.com/&xxe;</loc></url></urlset>'
    ).encode()
    doc = parse_sitemap(payload)
    assert all("TOP-SECRET" not in e.loc for e in doc.urls)
