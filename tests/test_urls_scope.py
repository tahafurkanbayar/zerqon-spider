from __future__ import annotations

import pytest

from zerqon.crawler.scope import CrawlScope, ScopeDecision
from zerqon.crawler.urls import (
    InvalidURLError,
    normalize_url,
    resolve_url,
    url_key,
    validate_start_url,
    variant_signature,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTP://Example.COM", "http://example.com/"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com/a/./b/../c", "https://example.com/a/c"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com/%7euser", "https://example.com/~user"),
        ("https://example.com/a%2fb", "https://example.com/a%2Fb"),
        ("https://example.com/ürün?q=çay", "https://example.com/%C3%BCr%C3%BCn?q=%C3%A7ay"),
        ("https://example.com/?b=2&a=1", "https://example.com/?b=2&a=1"),  # parametre sırası korunur
        ("https://bücher.example/", "https://xn--bcher-kva.example/"),
        ("https://example.com/dir/", "https://example.com/dir/"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("bad", ["ftp://example.com/", "javascript:alert(1)", "http://", "not a url"])
def test_normalize_rejects_invalid(bad: str) -> None:
    with pytest.raises(InvalidURLError):
        normalize_url(bad)


def test_resolve_url_relative_and_ignored_schemes() -> None:
    base = "https://example.com/blog/post"
    assert resolve_url(base, "../about") == "https://example.com/about"
    assert resolve_url(base, "//cdn.example.com/x.js") == "https://cdn.example.com/x.js"
    assert resolve_url(base, "#top") is None
    assert resolve_url(base, "mailto:a@b.c") is None
    assert resolve_url(base, "javascript:void(0)") is None
    assert resolve_url(base, "tel:+90") is None


def test_url_key_dedupes_equivalent_forms() -> None:
    assert url_key("https://EXAMPLE.com:443/a#x") == url_key("https://example.com/a")
    assert url_key("https://example.com/a") != url_key("https://example.com/a/")


def test_variant_signature_groups_variations() -> None:
    sig = variant_signature("https://example.com/Page/")
    assert sig == variant_signature("http://www.example.com/page")
    assert sig == variant_signature("https://example.com/page/index.html")
    assert variant_signature("https://e.com/x?b=1&a=2") == variant_signature("https://e.com/x?a=2&b=1")


def test_start_url_validation() -> None:
    assert validate_start_url("example.com") == "https://example.com/"
    with pytest.raises(InvalidURLError):
        validate_start_url("https://user:pass@example.com/")


def test_scope_rules() -> None:
    scope = CrawlScope("https://www.example.com/", exclude_patterns=r"/admin/" + "\n" + r"\?sort=")
    assert scope.decide("https://example.com/a") is ScopeDecision.IN_SCOPE
    assert scope.decide("http://www.example.com/a") is ScopeDecision.IN_SCOPE
    assert scope.decide("https://blog.example.com/") is ScopeDecision.EXTERNAL
    assert scope.decide("https://example.com.evil.com/") is ScopeDecision.EXTERNAL
    assert scope.decide("https://evilexample.com/") is ScopeDecision.EXTERNAL
    assert scope.decide("https://example.com/admin/x") is ScopeDecision.EXCLUDED
    assert scope.decide("https://example.com/list?sort=asc") is ScopeDecision.EXCLUDED

    sub = CrawlScope("https://example.com/", include_subdomains=True)
    assert sub.decide("https://blog.example.com/") is ScopeDecision.IN_SCOPE
    assert sub.decide("https://notexample.com/") is ScopeDecision.EXTERNAL


def test_scope_include_patterns_keep_start_url() -> None:
    scope = CrawlScope("https://example.com/", include_patterns=r"/blog/")
    assert scope.allows("https://example.com/")  # başlangıç her zaman
    assert scope.allows("https://example.com/blog/a")
    assert scope.decide("https://example.com/shop") is ScopeDecision.NOT_INCLUDED
