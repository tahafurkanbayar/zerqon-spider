"""Kontrol kaydı. Yeni bir kontrol eklemek için ilgili modülde fonksiyonu dekoratörle işaretlemek yeterlidir."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from zerqon.analysis.context import PageContext, SiteContext
from zerqon.crawler.store import IssueRecord

# (page_id, url, url_key, issue) — page_id None ise site geneli sorundur
SiteIssue = tuple[int | None, str | None, str | None, IssueRecord]
PageCheck = Callable[[PageContext], Iterable[IssueRecord]]
SiteCheck = Callable[[SiteContext], Iterable[SiteIssue]]

PAGE_CHECKS: list[PageCheck] = []
SITE_CHECKS: list[SiteCheck] = []


def page_check(fn: PageCheck) -> PageCheck:
    PAGE_CHECKS.append(fn)
    return fn


def site_check(fn: SiteCheck) -> SiteCheck:
    SITE_CHECKS.append(fn)
    return fn


def load_checks() -> None:
    """Kontrol modüllerini içe aktararak kayıt eder (idempotent)."""
    from zerqon.analysis import checks  # noqa: F401
