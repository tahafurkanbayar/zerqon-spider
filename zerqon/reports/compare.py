"""Aynı projeye ait iki taramanın karşılaştırılması.

- Sorunlar (kod, url_key) anahtarıyla eşleştirilir: yeni / çözülen / devam eden.
- URL'ler url_key ile eşleştirilir. Yeni taramada olmayan URL "artık keşfedilmedi" olarak raporlanır;
  bu, sayfanın silindiği anlamına GELMEZ (kapsam/limit/bağlantı değişmiş olabilir).
- İki taramanın ayar farkları ve tamamlanma durumları uyarı olarak döner.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from zerqon.db.repositories import crawls_repo, settings_repo
from zerqon.schemas import SETTINGS_FIELDS

MAX_LIST = 500
CHANGE_FIELDS: tuple[str, ...] = ("status", "title", "description", "canonical", "indexability")
SCOPE_FIELDS = frozenset(
    {"max_urls", "max_depth", "include_subdomains", "include_patterns", "exclude_patterns", "render_mode",
     "use_sitemaps", "allow_localhost", "user_agent"}
)


class CompareError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Comparison:
    a: dict[str, Any]
    b: dict[str, Any]
    snap_a: dict[str, Any]
    snap_b: dict[str, Any]
    settings_diff: list[tuple[str, Any, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues_new: list[dict[str, Any]] = field(default_factory=list)
    issues_resolved: list[dict[str, Any]] = field(default_factory=list)
    issues_persisting: int = 0
    issue_code_deltas: list[dict[str, Any]] = field(default_factory=list)
    urls_new: list[str] = field(default_factory=list)
    urls_missing: list[str] = field(default_factory=list)
    urls_new_total: int = 0
    urls_missing_total: int = 0
    changes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    change_totals: dict[str, int] = field(default_factory=dict)

    @property
    def score_delta(self) -> float | None:
        sa, sb = self.snap_a.get("health_score"), self.snap_b.get("health_score")
        return round(sb - sa, 1) if sa is not None and sb is not None else None


def _issue_keys(conn: sqlite3.Connection, crawl_id: int) -> dict[tuple[str, str], dict[str, Any]]:
    rows = conn.execute(
        "SELECT code, COALESCE(url_key, '') AS key, url, severity FROM issues WHERE crawl_id = ?", (crawl_id,)
    ).fetchall()
    return {(r["code"], r["key"]): dict(r) for r in rows}


def _pages(conn: sqlite3.Connection, crawl_id: int) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.url_key, p.url, p.status_code, p.fetch_status, p.indexability, p.indexability_reason,
               m.title, m.meta_description AS description, m.canonical
        FROM pages p LEFT JOIN page_metadata m ON m.page_id = p.id WHERE p.crawl_id = ?
        """,
        (crawl_id,),
    ).fetchall()
    return {r["url_key"]: dict(r) for r in rows}


def _value(page: dict[str, Any], name: str) -> Any:
    if name == "status":
        return page["status_code"] if page["status_code"] is not None else page["fetch_status"]
    if name == "indexability":
        return page["indexability"]
    return page[name]


def compare_crawls(conn: sqlite3.Connection, crawl_a: int, crawl_b: int) -> Comparison:
    a, b = crawls_repo.get_job(conn, crawl_a), crawls_repo.get_job(conn, crawl_b)
    if a is None or b is None:
        raise CompareError("crawl_not_found")
    if a["project_id"] != b["project_id"]:
        raise CompareError("different_projects")
    if a["id"] == b["id"]:
        raise CompareError("same_crawl")
    if a["id"] > b["id"]:
        a, b = b, a  # A her zaman eski tarama
    result = Comparison(a, b, crawls_repo.get_snapshot(conn, a["id"]) or {}, crawls_repo.get_snapshot(conn, b["id"]) or {})

    # --- Ayar farkları ve uyarılar
    sa, sb = settings_repo.get_settings(conn, a["settings_id"]), settings_repo.get_settings(conn, b["settings_id"])
    for name in SETTINGS_FIELDS:
        va, vb = getattr(sa, name), getattr(sb, name)
        if va != vb:
            result.settings_diff.append((name, va, vb))
    if any(name in SCOPE_FIELDS for name, _, _ in result.settings_diff):
        result.warnings.append("scope_changed")
    if any(name.endswith(("_chars", "_count", "_bytes", "_length", "_depth")) and name not in SCOPE_FIELDS for name, _, _ in result.settings_diff):
        result.warnings.append("thresholds_changed")
    for job, tag in ((a, "a"), (b, "b")):
        if job["status"] != "completed":
            result.warnings.append(f"partial_{tag}")
        if job["limit_reached"]:
            result.warnings.append(f"limit_{tag}")
    if a["start_url"] != b["start_url"]:
        result.warnings.append("start_url_changed")

    # --- Sorunlar
    ia, ib = _issue_keys(conn, a["id"]), _issue_keys(conn, b["id"])
    new_keys = ib.keys() - ia.keys()
    resolved_keys = ia.keys() - ib.keys()
    result.issues_persisting = len(ia.keys() & ib.keys())
    result.issues_new = sorted((ib[k] for k in new_keys), key=lambda r: (r["code"], r["url"] or ""))[:MAX_LIST]
    result.issues_resolved = sorted((ia[k] for k in resolved_keys), key=lambda r: (r["code"], r["url"] or ""))[:MAX_LIST]
    count_a, count_b = Counter(code for code, _ in ia), Counter(code for code, _ in ib)
    result.issue_code_deltas = sorted(
        (
            {"code": code, "a": count_a.get(code, 0), "b": count_b.get(code, 0), "delta": count_b.get(code, 0) - count_a.get(code, 0)}
            for code in set(count_a) | set(count_b)
            if count_a.get(code, 0) != count_b.get(code, 0)
        ),
        key=lambda r: (-abs(r["delta"]), r["code"]),
    )

    # --- URL'ler ve alan değişimleri
    pa, pb = _pages(conn, a["id"]), _pages(conn, b["id"])
    new_urls = sorted(pb[k]["url"] for k in pb.keys() - pa.keys())
    missing_urls = sorted(pa[k]["url"] for k in pa.keys() - pb.keys())
    result.urls_new_total, result.urls_missing_total = len(new_urls), len(missing_urls)
    result.urls_new, result.urls_missing = new_urls[:MAX_LIST], missing_urls[:MAX_LIST]
    for name in CHANGE_FIELDS:
        changed = [
            {"url": pb[k]["url"], "old": _value(pa[k], name), "new": _value(pb[k], name)}
            for k in pa.keys() & pb.keys()
            if _value(pa[k], name) != _value(pb[k], name)
        ]
        changed.sort(key=lambda r: r["url"])
        result.change_totals[name] = len(changed)
        result.changes[name] = changed[:MAX_LIST]
    return result
