"""Bağlama duyarlı önceliklendirme (bkz. ADR-011, docs/SCORING.md).

Her sorunun `base_severity` değeri registry'den gelir. Tarama sonunda aşağıdaki kurallarla
`severity` yeniden hesaplanır (deterministik, her çalıştırmada base_severity'den başlar):

1. Yaygınlık (sunucu hataları): status_5xx / fetch_error HTML sayfaların ≥%10'unu veya ≥10 URL'yi
   etkiliyorsa → critical.
2. Yaygınlık (kırık): status_4xx / broken_internal_link etkilenen oran ≥%10 ise bir seviye yükselir.
3. Sayfa önemi: başlangıç sayfası, sitemap'te bulunan veya çok bağlantı alan (≥10 ya da ilk %10)
   sayfalarda IMPORTANCE_SENSITIVE kodlar bir seviye yükselir. Özellikle önemli sayfadaki `noindex`
   "muhtemelen istenmeyen noindex" olarak high olur.
4. Indexlenemez bağlam: meta/içerik kodları indexlenemeyen sayfalarda bir seviye düşer.
5. Şablon geneli: low seviyeli meta/içerik sorunu indexlenebilir sayfaların ≥%50'sinde (en az 5 sayfa)
   görülüyorsa medium'a yükselir.
priority_score sıralama içindir: seviye ağırlığı + log(gelen bağlantı) + sitemap katkısı.
"""

from __future__ import annotations

import math
import sqlite3
from collections import Counter

from zerqon.crawler.store import SEVERITY_RANK
from zerqon.db.connection import transaction

ORDER: tuple[str, ...] = ("critical", "high", "medium", "low", "info")

SERVER_ERROR_CODES = frozenset({"status_5xx", "fetch_error"})
BROKEN_CODES = frozenset({"status_4xx", "broken_internal_link"})
IMPORTANCE_SENSITIVE = frozenset(
    {
        "status_4xx", "status_5xx", "noindex", "canonical_target_error", "canonical_target_noindex",
        "canonical_invalid", "canonical_multiple", "title_missing", "h1_missing", "robots_changed_by_js",
        "redirect_to_error", "blocked_by_robots",
    }
)
CONTEXT_SENSITIVE_CATEGORIES = frozenset({"title", "description", "headings", "content", "social", "images"})
TEMPLATE_WIDE_CODES = frozenset(
    {
        "title_too_short", "title_too_long", "description_too_short", "description_too_long", "description_multiple",
        "h1_multiple", "thin_content", "image_missing_alt", "og_missing", "description_missing", "h1_missing",
    }
)


def shift(severity: str, steps: int) -> str:
    """steps < 0: yükselt (daha ciddi), steps > 0: düşür."""
    idx = min(len(ORDER) - 1, max(0, ORDER.index(severity) + steps))
    return ORDER[idx]


def prioritize(conn: sqlite3.Connection, crawl_id: int) -> None:
    html_total = conn.execute(
        "SELECT COUNT(*) FROM pages WHERE crawl_id = ? AND (is_html = 1 OR status_code >= 400 OR fetch_status = 'error')",
        (crawl_id,),
    ).fetchone()[0] or 1
    indexable_total = conn.execute(
        "SELECT COUNT(*) FROM pages WHERE crawl_id = ? AND indexability = 'indexable'", (crawl_id,)
    ).fetchone()[0] or 1
    inlinks_sorted = sorted(
        r[0] for r in conn.execute("SELECT inlinks FROM pages WHERE crawl_id = ? AND is_html = 1", (crawl_id,))
    )
    top_threshold = max(10, inlinks_sorted[int(len(inlinks_sorted) * 0.9)] if inlinks_sorted else 10)

    rows = conn.execute(
        """
        SELECT i.id, i.code, i.category, i.base_severity, i.page_id,
               p.inlinks, p.in_sitemap, p.source, p.indexability
        FROM issues i LEFT JOIN pages p ON p.id = i.page_id WHERE i.crawl_id = ?
        """,
        (crawl_id,),
    ).fetchall()
    per_code = Counter(r["code"] for r in rows if r["page_id"] is not None)

    updates: list[tuple[str, int, float, int]] = []
    for r in rows:
        sev = r["base_severity"]
        code = r["code"]
        count = per_code.get(code, 0)
        ratio = count / html_total
        if code in SERVER_ERROR_CODES and (ratio >= 0.1 or count >= 10):
            sev = "critical"
        elif code in BROKEN_CODES and ratio >= 0.1:
            sev = shift(sev, -1)
        if r["page_id"] is not None:
            important = r["source"] == "seed" or bool(r["in_sitemap"]) or (r["inlinks"] or 0) >= top_threshold
            if code == "noindex" and important:
                sev = "high"
            elif code in IMPORTANCE_SENSITIVE and important and sev != "critical":
                sev = shift(sev, -1)
            if r["category"] in CONTEXT_SENSITIVE_CATEGORIES and r["indexability"] == "non_indexable":
                sev = shift(sev, 1)
            elif code in TEMPLATE_WIDE_CODES and sev == "low" and count >= 5 and count / indexable_total >= 0.5:
                sev = "medium"
        rank = SEVERITY_RANK[sev]
        score = (6 - rank) * 20 + min(20.0, math.log2(1 + (r["inlinks"] or 0)) * 4) + (5 if r["in_sitemap"] else 0)
        updates.append((sev, rank, round(score, 2), r["id"]))

    with transaction(conn):
        conn.executemany("UPDATE issues SET severity = ?, severity_rank = ?, priority_score = ? WHERE id = ?", updates)
        conn.execute(
            """
            UPDATE pages SET issues_count = COALESCE(
                (SELECT COUNT(*) FROM issues i WHERE i.page_id = pages.id AND i.severity <> 'info'), 0)
            WHERE crawl_id = ?
            """,
            (crawl_id,),
        )
