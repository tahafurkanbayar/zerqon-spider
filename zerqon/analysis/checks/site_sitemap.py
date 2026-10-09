"""Site düzeyi kontroller: robots.txt, sitemap ve hreflang ilişkileri."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from zerqon.analysis.context import SiteContext
from zerqon.analysis.issues import issue
from zerqon.analysis.registry import SiteIssue, site_check
from zerqon.crawler.urls import url_key


@site_check
def robots_and_sitemaps(ctx: SiteContext) -> Iterator[SiteIssue]:
    job = ctx.conn.execute(
        "SELECT robots_status, robots_url FROM crawl_jobs WHERE id = ?", (ctx.crawl_id,)
    ).fetchone()
    robots_status = job["robots_status"] if job else None
    robots_url = job["robots_url"] if job else None
    if robots_status == "unavailable":
        yield None, robots_url, None, issue("robots_unavailable", robots_url)
    elif robots_status == "not_found":
        yield None, robots_url, None, issue("robots_missing", robots_url)

    if not ctx.settings.use_sitemaps:
        return
    sitemaps = ctx.conn.execute(
        "SELECT url, source, status_code, kind, error_code, error_detail FROM sitemaps WHERE crawl_id = ?",
        (ctx.crawl_id,),
    ).fetchall()
    usable = [s for s in sitemaps if s["kind"] in ("urlset", "index", "text")]
    if not usable:
        yield None, None, None, issue("sitemap_missing", "robots.txt Sitemap: — · /sitemap.xml: —")
    for s in sitemaps:
        if s["kind"] == "invalid":
            yield None, s["url"], url_key(s["url"]), issue("sitemap_invalid", s["error_detail"] or s["error_code"])
        elif s["error_code"] and s["error_code"] not in ("truncated", "out_of_scope") and s["source"] != "default":
            detail = f"HTTP {s['status_code']}" if s["status_code"] else (s["error_detail"] or s["error_code"])
            yield None, s["url"], url_key(s["url"]), issue("sitemap_error", detail, error=s["error_code"])
    if usable and all(s["source"] == "default" for s in usable):
        yield None, usable[0]["url"], url_key(usable[0]["url"]), issue("sitemap_not_in_robots", usable[0]["url"])


@site_check
def sitemap_urls(ctx: SiteContext) -> Iterator[SiteIssue]:
    rows = ctx.conn.execute(
        """
        SELECT p.id, p.url, p.url_key, p.status_code, p.fetch_status, p.indexability_reason, m.canonical
        FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id
        WHERE p.crawl_id = ? AND p.in_sitemap = 1
        """,
        (ctx.crawl_id,),
    ).fetchall()
    for r in rows:
        status = r["status_code"]
        if r["fetch_status"] == "blocked_robots":
            yield r["id"], r["url"], r["url_key"], issue("sitemap_url_blocked", "robots.txt: Disallow")
        elif r["fetch_status"] == "error" or status is None or not 200 <= status < 300:
            yield r["id"], r["url"], r["url_key"], issue(
                "sitemap_url_non_200", f"{status or r['fetch_status']}", status=status
            )
        elif r["indexability_reason"] == "noindex":
            yield r["id"], r["url"], r["url_key"], issue("sitemap_url_noindex", "noindex")
        elif r["indexability_reason"] == "canonicalised":
            yield r["id"], r["url"], r["url_key"], issue("sitemap_url_non_canonical", f"canonical → {r['canonical']}")


@site_check
def hreflang_relations(ctx: SiteContext) -> Iterator[SiteIssue]:
    rows = ctx.conn.execute(
        """
        SELECT h.page_id, p.url, p.url_key, h.lang, h.href, h.href_key
        FROM hreflang h JOIN pages p ON p.id = h.page_id WHERE p.crawl_id = ?
        """,
        (ctx.crawl_id,),
    ).fetchall()
    if not rows:
        return
    targets_of: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        targets_of[r["url_key"]].add(r["href_key"])
    pages = {
        r["url_key"]: r
        for r in ctx.conn.execute(
            "SELECT url_key, status_code, fetch_status, indexability_reason FROM pages WHERE crawl_id = ?",
            (ctx.crawl_id,),
        )
    }
    errors: dict[int, list[str]] = defaultdict(list)
    no_return: dict[int, list[str]] = defaultdict(list)
    non_canonical: dict[int, list[str]] = defaultdict(list)
    meta: dict[int, tuple[str, str]] = {}
    for r in rows:
        meta[r["page_id"]] = (r["url"], r["url_key"])
        if r["href_key"] == r["url_key"]:
            continue
        target = pages.get(r["href_key"])
        if target is None:
            continue  # taranmadı (kapsam dışı/limit): kesin yargı yok
        status = target["status_code"] or 0
        label = f"{r['lang']}: {r['href']}"
        if target["fetch_status"] != "ok" or not 200 <= status < 300:
            errors[r["page_id"]].append(f"{label} ({status or target['fetch_status']})")
        elif target["indexability_reason"] in ("noindex", "canonicalised"):
            non_canonical[r["page_id"]].append(f"{label} ({target['indexability_reason']})")
        elif r["url_key"] not in targets_of.get(r["href_key"], set()):
            no_return[r["page_id"]].append(label)
    for code, bucket in (
        ("hreflang_target_error", errors),
        ("hreflang_no_return", no_return),
        ("hreflang_target_non_canonical", non_canonical),
    ):
        for pid, items in bucket.items():
            url, key = meta[pid]
            yield pid, url, key, issue(code, "\n".join(items[:5]), count=len(items))
