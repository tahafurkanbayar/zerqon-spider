"""Site düzeyi kontroller: yönlendirmeler, kırık bağlantılar, URL varyasyonları, derinlik, yetim adaylar."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from zerqon.analysis.context import SiteContext
from zerqon.analysis.issues import issue
from zerqon.analysis.registry import SiteIssue, site_check
from zerqon.crawler.postprocess import follow_chain
from zerqon.crawler.urls import variant_signature


def _sample(values: list[str], limit: int = 5) -> str:
    more = len(values) - limit
    return "\n".join(values[:limit]) + (f"\n… (+{more})" if more > 0 else "")


@site_check
def redirects(ctx: SiteContext) -> Iterator[SiteIssue]:
    pages = {
        r["url_key"]: r
        for r in ctx.conn.execute(
            "SELECT id, url, url_key, status_code, redirect_url, redirect_type FROM pages WHERE crawl_id = ?",
            (ctx.crawl_id,),
        )
    }
    for key, page in pages.items():
        if not page["redirect_url"]:
            continue
        chain = follow_chain(key, pages)
        path = " → ".join([chain.hops[0][0]] + [hop[1] for hop in chain.hops]) if chain.hops else ""
        if chain.loop:
            yield page["id"], page["url"], key, issue("redirect_loop", path, hops=len(chain.hops))
            continue
        if len(chain.hops) > 1:
            yield page["id"], page["url"], key, issue("redirect_chain", path, hops=len(chain.hops))
        if chain.final_status is not None and chain.final_status >= 400:
            yield page["id"], page["url"], key, issue(
                "redirect_to_error", f"{path} ({chain.final_status})", final_status=chain.final_status
            )


@site_check
def internal_link_targets(ctx: SiteContext) -> Iterator[SiteIssue]:
    rows = ctx.conn.execute(
        """
        SELECT s.id AS source_id, s.url AS source_url, s.url_key AS source_key,
               t.url AS target_url, t.status_code, t.fetch_status, t.error_code
        FROM links l
        JOIN pages s ON s.id = l.source_page_id
        JOIN pages t ON t.crawl_id = l.crawl_id AND t.url_key = l.target_key
        WHERE l.crawl_id = ? AND l.is_internal = 1
          AND (t.status_code >= 300 OR t.fetch_status = 'error')
        GROUP BY s.id, t.id
        """,
        (ctx.crawl_id,),
    ).fetchall()
    broken: dict[int, list[str]] = defaultdict(list)
    redirected: dict[int, list[str]] = defaultdict(list)
    meta: dict[int, tuple[str, str]] = {}
    for r in rows:
        meta[r["source_id"]] = (r["source_url"], r["source_key"])
        if r["fetch_status"] == "error" or (r["status_code"] or 0) >= 400:
            broken[r["source_id"]].append(f"{r['target_url']} ({r['status_code'] or r['error_code']})")
        else:
            redirected[r["source_id"]].append(f"{r['target_url']} ({r['status_code']})")
    for pid, targets in broken.items():
        url, key = meta[pid]
        yield pid, url, key, issue("broken_internal_link", _sample(targets), count=len(targets))
    for pid, targets in redirected.items():
        url, key = meta[pid]
        yield pid, url, key, issue("internal_link_to_redirect", _sample(targets), count=len(targets))


@site_check
def url_variants(ctx: SiteContext) -> Iterator[SiteIssue]:
    groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in ctx.conn.execute(
        "SELECT id, url, url_key FROM pages WHERE crawl_id = ? AND status_code BETWEEN 200 AND 299 AND is_html = 1",
        (ctx.crawl_id,),
    ):
        groups[variant_signature(r["url"])].append((r["id"], r["url"], r["url_key"]))
    for members in groups.values():
        if len(members) < 2:
            continue
        schemes = {url.split(":", 1)[0] for _, url, _ in members}
        code = "http_https_duplicate" if len(schemes) > 1 else "url_variant_duplicates"
        evidence = _sample([url for _, url, _ in members])
        for pid, url, key in members:
            yield pid, url, key, issue(code, evidence, variants=len(members))


@site_check
def depth_and_orphans(ctx: SiteContext) -> Iterator[SiteIssue]:
    for r in ctx.conn.execute(
        "SELECT id, url, url_key, crawl_depth FROM pages WHERE crawl_id = ? AND crawl_depth > ?"
        " AND indexability = 'indexable'",
        (ctx.crawl_id, ctx.settings.deep_page_depth),
    ):
        yield r["id"], r["url"], r["url_key"], issue(
            "deep_page", f"{r['crawl_depth']}", depth=r["crawl_depth"], threshold=ctx.settings.deep_page_depth
        )
    # Sitemap'te olup taranan hiçbir sayfadan bağlantı almayan URL'ler: kesin değil, ADAY
    for r in ctx.conn.execute(
        "SELECT id, url, url_key FROM pages WHERE crawl_id = ? AND in_sitemap = 1 AND inlinks = 0"
        " AND source <> 'seed'",
        (ctx.crawl_id,),
    ):
        yield r["id"], r["url"], r["url_key"], issue("orphan_candidate", "sitemap: evet · gelen bağlantı: 0")
