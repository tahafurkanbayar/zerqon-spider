"""Teknik SEO sağlık puanı (0-100) ve güvenilirlik — bkz. docs/SCORING.md, ADR-012.

Bu puan Zerqon Spider'ın kendi deterministik modelidir; Google'ın veya başka bir arama motorunun
resmi değerlendirmesi DEĞİLDİR.

    score = 100 × Π_(kod, önem) (1 − w[önem] × √oran)

- oran = o kod/önem için etkilenen URL sayısı / analiz edilen URL sayısı (site geneli sorunlarda 1)
- w = {critical: 0.25, high: 0.12, medium: 0.05, low: 0.015, info: 0}
Karekök, az sayıda sayfayı etkileyen sorunların da görünür ceza almasını sağlar; çarpım modeli puanın
0'ın altına düşmesini engeller ve aynı veride her zaman aynı sonucu verir.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from typing import Any

WEIGHTS: dict[str, float] = {"critical": 0.25, "high": 0.12, "medium": 0.05, "low": 0.015, "info": 0.0}
CONFIDENCE_WEIGHTS: dict[str, int] = {
    "partial_crawl": 2,
    "url_limit": 1,
    "few_pages": 1,
    "very_few_pages": 2,
    "many_errors": 1,
    "robots_blocked": 1,
    "robots_unavailable": 2,
    "no_html": 3,
}


@dataclass
class ScoreResult:
    score: float | None
    confidence: str
    reasons: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)


def score_from_groups(groups: list[tuple[str, str, int, bool]], analyzed: int) -> tuple[float, dict[str, float]]:
    """groups: (kategori, önem, etkilenen URL sayısı, site_geneli). Puan ve kategori alt puanlarını döndürür."""
    total = 1.0
    per_category: dict[str, float] = {}
    for category, severity, affected, site_wide in groups:
        weight = WEIGHTS.get(severity, 0.0)
        if weight == 0:
            continue
        ratio = 1.0 if site_wide else min(1.0, affected / max(1, analyzed))
        factor = 1.0 - weight * math.sqrt(ratio)
        total *= factor
        per_category[category] = per_category.get(category, 1.0) * factor
    return round(100 * total, 1), {k: round(100 * v, 1) for k, v in per_category.items()}


def confidence_level(reasons: list[str]) -> str:
    points = sum(CONFIDENCE_WEIGHTS.get(r, 1) for r in reasons)
    if points == 0:
        return "high"
    if points <= 2:
        return "medium"
    return "low"


def compute_score(conn: sqlite3.Connection, crawl_id: int) -> ScoreResult:
    job = conn.execute(
        "SELECT status, limit_reached, robots_status FROM crawl_jobs WHERE id = ?", (crawl_id,)
    ).fetchone()
    counts = conn.execute(
        """
        SELECT COUNT(*) AS total, SUM(is_html) AS html,
               SUM(CASE WHEN fetch_status IN ('error', 'blocked_security') OR status_code >= 500 THEN 1 ELSE 0 END) AS errors,
               SUM(CASE WHEN fetch_status = 'blocked_robots' THEN 1 ELSE 0 END) AS blocked
        FROM pages WHERE crawl_id = ?
        """,
        (crawl_id,),
    ).fetchone()
    total, html = counts["total"] or 0, counts["html"] or 0
    errors, blocked = counts["errors"] or 0, counts["blocked"] or 0

    reasons: list[str] = []
    if job and job["status"] in ("stopping", "cancelled", "interrupted", "failed"):
        reasons.append("partial_crawl")
    if job and job["limit_reached"]:
        reasons.append("url_limit")
    if job and job["robots_status"] == "unavailable":
        reasons.append("robots_unavailable")
    if html == 0:
        reasons.append("no_html")
    elif html < 3:
        reasons.append("very_few_pages")
    elif html < 10:
        reasons.append("few_pages")
    if total and errors / total > 0.2:
        reasons.append("many_errors")
    if total and blocked / total > 0.3:
        reasons.append("robots_blocked")

    if total == 0:
        return ScoreResult(None, "low", reasons or ["no_html"])

    # Analiz edilen URL: HTML sayfalar + hata veren URL'ler (sorun üretebilen evren)
    analyzed = conn.execute(
        "SELECT COUNT(*) FROM pages WHERE crawl_id = ? AND (is_html = 1 OR status_code >= 400 OR fetch_status <> 'ok')",
        (crawl_id,),
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT category, severity, COUNT(DISTINCT page_id) AS affected, MAX(page_id IS NULL) AS site_wide
        FROM issues WHERE crawl_id = ? GROUP BY code, category, severity
        """,
        (crawl_id,),
    ).fetchall()
    groups = [(r["category"], r["severity"], r["affected"], bool(r["site_wide"])) for r in rows]
    score, categories = score_from_groups(groups, analyzed)
    breakdown = {"analyzed_urls": analyzed, "categories": categories, "weights": WEIGHTS}
    return ScoreResult(score, confidence_level(reasons), reasons, breakdown)


def snapshot_fields(result: ScoreResult) -> dict[str, Any]:
    return {
        "health_score": result.score,
        "score_confidence": result.confidence,
        "confidence_reasons": ",".join(result.reasons) or None,
        "score_breakdown": json.dumps(result.breakdown, separators=(",", ":")),
    }
