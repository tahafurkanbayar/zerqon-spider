"""Tarama kapsamı (bkz. ADR-008).

Kapsam dışı URL'ler kayıt altına alınır ama asla getirilmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

from zerqon.crawler.urls import host_of, strip_www

_MAX_REGEX_INPUT = 4096


class ScopeDecision(StrEnum):
    IN_SCOPE = "in_scope"
    EXTERNAL = "external"
    EXCLUDED = "excluded"
    NOT_INCLUDED = "not_included"
    BAD_SCHEME = "bad_scheme"


def _compile(patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(line.strip()) for line in (patterns or "").splitlines() if line.strip()]


@dataclass
class CrawlScope:
    start_url: str
    include_subdomains: bool = False
    include_patterns: str = ""
    exclude_patterns: str = ""
    base_host: str = field(init=False)
    _include: list[re.Pattern[str]] = field(init=False, repr=False)
    _exclude: list[re.Pattern[str]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_host = strip_www(host_of(self.start_url))
        self._include = _compile(self.include_patterns)
        self._exclude = _compile(self.exclude_patterns)

    def is_internal_host(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if host in (self.base_host, f"www.{self.base_host}"):
            return True
        return self.include_subdomains and host.endswith(f".{self.base_host}")

    def is_internal(self, url: str) -> bool:
        return self.is_internal_host(host_of(url))

    def decide(self, url: str) -> ScopeDecision:
        if urlsplit(url).scheme not in ("http", "https"):
            return ScopeDecision.BAD_SCHEME
        if not self.is_internal(url):
            return ScopeDecision.EXTERNAL
        subject = url[:_MAX_REGEX_INPUT]
        if any(p.search(subject) for p in self._exclude):
            return ScopeDecision.EXCLUDED
        if self._include and not any(p.search(subject) for p in self._include):
            # Başlangıç URL'si dahil etme kuralına uymasa da taranır (aksi halde tarama başlayamaz)
            if url != self.start_url:
                return ScopeDecision.NOT_INCLUDED
        return ScopeDecision.IN_SCOPE

    def allows(self, url: str) -> bool:
        return self.decide(url) is ScopeDecision.IN_SCOPE
