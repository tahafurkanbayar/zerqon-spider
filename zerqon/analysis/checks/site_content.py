"""Site düzeyi kontroller: yinelenen meta veriler, yinelenen/benzer içerik, canonical hedefleri, görseller."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from urllib.parse import urlsplit

from zerqon.analysis.context import SiteContext
from zerqon.analysis.issues import issue
from zerqon.analysis.registry import SiteIssue, site_check
from zerqon.crawler.urls import variant_signature
from zerqon.parsing.text import hamming, simhash_bands

NEAR_DUPLICATE_MAX_DISTANCE = 3
LEGACY_IMAGE_TYPES = ("image/bmp", "image/tiff", "image/x-icon")


def _sample(values: list[str], limit: int = 5) -> str:
    more = len(values) - limit
    return "\n".join(values[:limit]) + (f"\n… (+{more})" if more > 0 else "")


def _duplicates(ctx: SiteContext, column: str, code: str) -> Iterator[SiteIssue]:
    # column sabit bir beyaz listeden gelir (aşağıdaki çağrılar)
    rows = ctx.conn.execute(
        f"""
        SELECT p.id, p.url, p.url_key, m.{column} AS value FROM pages p JOIN page_metadata m ON m.page_id = p.id
        WHERE p.crawl_id = ? AND p.indexability = 'indexable' AND m.{column} IS NOT NULL AND m.{column} <> ''
        """,  # noqa: S608
        (ctx.crawl_id,),
    ).fetchall()
    groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in rows:
        groups[r["value"].strip().casefold()].append((r["id"], r["url"], r["url_key"]))
    for value, members in groups.items():
        if len(members) < 2:
            continue
        evidence = f"\"{value[:150]}\"\n" + _sample([url for _, url, _ in members])
        for pid, url, key in members:
            yield pid, url, key, issue(code, evidence, duplicates=len(members))


@site_check
def duplicate_metadata(ctx: SiteContext) -> Iterator[SiteIssue]:
    yield from _duplicates(ctx, "title", "title_duplicate")
    yield from _duplicates(ctx, "meta_description", "description_duplicate")
    yield from _duplicates(ctx, "h1", "h1_duplicate")


@site_check
def duplicate_content(ctx: SiteContext) -> Iterator[SiteIssue]:
    rows = ctx.conn.execute(
        "SELECT id, url, url_key, text_hash, simhash, word_count FROM pages WHERE crawl_id = ?"
        " AND indexability = 'indexable' AND text_hash IS NOT NULL",
        (ctx.crawl_id,),
    ).fetchall()
    exact: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in rows:
        exact[r["text_hash"]].append((r["id"], r["url"], r["url_key"]))
    exact_ids: set[int] = set()
    for members in exact.values():
        if len(members) < 2:
            continue
        evidence = _sample([url for _, url, _ in members])
        for pid, url, key in members:
            exact_ids.add(pid)
            yield pid, url, key, issue("duplicate_content", evidence, duplicates=len(members))

    # SimHash + LSH bantları: yalnızca aynı bantta eşleşen adaylar karşılaştırılır (bkz. ADR-013)
    candidates = [r for r in rows if r["simhash"] is not None and (r["word_count"] or 0) >= 50]
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, r in enumerate(candidates):
        for band in simhash_bands(r["simhash"]):
            buckets[band].append(idx)
    similar: dict[int, set[int]] = defaultdict(set)
    for members in buckets.values():
        if len(members) < 2 or len(members) > 500:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                ra, rb = candidates[a], candidates[b]
                if ra["text_hash"] == rb["text_hash"]:
                    continue
                if hamming(ra["simhash"], rb["simhash"]) <= NEAR_DUPLICATE_MAX_DISTANCE:
                    similar[a].add(b)
                    similar[b].add(a)
    for idx, others in similar.items():
        r = candidates[idx]
        evidence = _sample([candidates[o]["url"] for o in sorted(others)])
        yield r["id"], r["url"], r["url_key"], issue("near_duplicate_candidate", evidence, similar=len(others))


@site_check
def canonical_targets(ctx: SiteContext) -> Iterator[SiteIssue]:
    rows = ctx.conn.execute(
        """
        SELECT p.id, p.url, p.url_key, m.canonical, t.status_code AS t_status, t.fetch_status AS t_fetch,
               t.indexability_reason AS t_reason, tm.canonical_key AS t_canonical_key, t.url_key AS t_key
        FROM pages p
        JOIN page_metadata m ON m.page_id = p.id
        LEFT JOIN pages t ON t.crawl_id = p.crawl_id AND t.url_key = m.canonical_key
        LEFT JOIN page_metadata tm ON tm.page_id = t.id
        WHERE p.crawl_id = ? AND m.canonical_key IS NOT NULL AND m.canonical_key <> p.url_key
        """,
        (ctx.crawl_id,),
    ).fetchall()
    for r in rows:
        if r["t_key"] is None:
            continue  # hedef taranmadı (kapsam dışı/limit) — kesin yargı yok
        evidence = f"{r['url']} → {r['canonical']} ({r['t_status'] or r['t_fetch']})"
        status = r["t_status"] or 0
        if r["t_fetch"] == "error" or status >= 400:
            yield r["id"], r["url"], r["url_key"], issue("canonical_target_error", evidence, target_status=status)
        elif 300 <= status < 400:
            yield r["id"], r["url"], r["url_key"], issue("canonical_target_redirect", evidence, target_status=status)
        elif r["t_reason"] == "noindex":
            yield r["id"], r["url"], r["url_key"], issue("canonical_target_noindex", evidence)
        elif r["t_canonical_key"] and r["t_canonical_key"] != r["t_key"]:
            yield r["id"], r["url"], r["url_key"], issue("canonical_target_canonicalised", evidence)

    # Canonical eksikliği yalnızca bağlamda sorun: parametreli URL veya varyasyon grubu varsa
    rows = ctx.conn.execute(
        """
        SELECT p.id, p.url, p.url_key FROM pages p JOIN page_metadata m ON m.page_id = p.id
        WHERE p.crawl_id = ? AND p.indexability = 'indexable' AND m.canonical_count = 0
        """,
        (ctx.crawl_id,),
    ).fetchall()
    signatures: dict[str, int] = defaultdict(int)
    for r in ctx.conn.execute(
        "SELECT url FROM pages WHERE crawl_id = ? AND is_html = 1 AND status_code BETWEEN 200 AND 299", (ctx.crawl_id,)
    ):
        signatures[variant_signature(r["url"])] += 1
    for r in rows:
        has_params = bool(urlsplit(r["url"]).query)
        has_variants = signatures.get(variant_signature(r["url"]), 0) > 1
        if has_params or has_variants:
            yield r["id"], r["url"], r["url_key"], issue(
                "canonical_missing_on_variant", r["url"], has_params=has_params, has_variants=has_variants
            )


@site_check
def image_resources(ctx: SiteContext) -> Iterator[SiteIssue]:
    rows = ctx.conn.execute(
        """
        SELECT p.id, p.url, p.url_key, r.url AS img, r.status_code, r.size_bytes, r.content_type, r.error_code
        FROM images i
        JOIN image_resources r ON r.crawl_id = i.crawl_id AND r.src_key = i.src_key
        JOIN pages p ON p.id = i.page_id
        WHERE i.crawl_id = ?
        """,
        (ctx.crawl_id,),
    ).fetchall()
    per_page: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    meta: dict[int, tuple[str, str]] = {}
    for r in rows:
        meta[r["id"]] = (r["url"], r["url_key"])
        if r["error_code"] and r["error_code"] != "blocked_robots" or (r["status_code"] or 0) >= 400:
            per_page["image_broken"][r["id"]].append(f"{r['img']} ({r['status_code'] or r['error_code']})")
        elif r["size_bytes"] and r["size_bytes"] > ctx.settings.large_image_bytes:
            per_page["image_too_large"][r["id"]].append(f"{r['img']} ({r['size_bytes'] // 1024} KB)")
        if (r["content_type"] or "").split(";")[0].strip() in LEGACY_IMAGE_TYPES:
            per_page["image_legacy_format"][r["id"]].append(f"{r['img']} ({r['content_type']})")
    for code, pages in per_page.items():
        for pid, items in pages.items():
            url, key = meta[pid]
            yield pid, url, key, issue(code, _sample(sorted(set(items))), count=len(set(items)))

    # Aynı görselin yalnızca sorgu dizesi/büyük-küçük harf farkıyla farklı URL'lerle kullanılması
    groups: dict[str, set[str]] = defaultdict(set)
    for r in ctx.conn.execute("SELECT DISTINCT src FROM images WHERE crawl_id = ? AND is_internal = 1", (ctx.crawl_id,)):
        parts = urlsplit(r["src"])
        groups[f"{parts.netloc.lower()}{parts.path.lower()}"].add(r["src"])
    for variants in groups.values():
        if len(variants) > 1:
            yield None, None, None, issue("image_duplicate_variants", _sample(sorted(variants)), variants=len(variants))
