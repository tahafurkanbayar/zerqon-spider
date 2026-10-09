"""Tek dosyalık, çevrimdışı açılabilen HTML denetim raporu.

- Harici CSS/JS/font/CDN yok; logo satır içi SVG.
- Jinja2 autoescape açık: site kaynaklı tüm veriler (title, URL, kanıt…) escape edilir.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from zerqon import PRODUCT_DESCRIPTION, PRODUCT_NAME, SLOGAN, __version__
from zerqon.db.connection import utcnow_iso
from zerqon.db.repositories import crawls_repo, issues_repo, projects_repo, settings_repo
from zerqon.formatting import fmt_bytes, fmt_datetime, fmt_number, status_class
from zerqon.i18n import Translator
from zerqon.reports.csv_export import safe_filename

TEMPLATES = Path(__file__).parent / "templates"
LOGO_PATH = Path(__file__).resolve().parent.parent / "web" / "static" / "img" / "logo-mark.svg"
TOP_GROUPS = 25
SAMPLES_PER_GROUP = 10

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters.update(number=fmt_number, dt=fmt_datetime, bytes=fmt_bytes, status_class=status_class)


def _logo_svg() -> Markup:
    # Güvenilir, paket içi statik dosya
    return Markup(LOGO_PATH.read_text(encoding="utf-8").replace('role="img"', 'role="img" width="56" height="56"'))  # noqa: S704


def collect_report_data(conn: sqlite3.Connection, crawl_id: int) -> dict[str, Any]:
    job = crawls_repo.get_job(conn, crawl_id)
    if job is None:
        raise LookupError(f"crawl {crawl_id}")
    project = projects_repo.get_project(conn, job["project_id"])
    settings = settings_repo.get_settings(conn, job["settings_id"])
    snapshot = crawls_repo.get_snapshot(conn, crawl_id) or {}
    groups = issues_repo.summary(conn, crawl_id)
    detailed = [g for g in groups if g["severity"] != "info"][:TOP_GROUPS]
    for group in detailed:
        group["samples"], _ = issues_repo.by_code(conn, crawl_id, group["code"], per_page=SAMPLES_PER_GROUP)
    breakdown = json.loads(snapshot["score_breakdown"]) if snapshot.get("score_breakdown") else {}
    reasons = [r for r in (snapshot.get("confidence_reasons") or "").split(",") if r]
    index_reasons = [
        dict(r) for r in conn.execute(
            "SELECT indexability_reason AS reason, COUNT(*) AS n FROM pages WHERE crawl_id = ?"
            " AND indexability = 'non_indexable' GROUP BY indexability_reason ORDER BY n DESC",
            (crawl_id,),
        )
    ]
    sitemaps = [dict(r) for r in conn.execute(
        "SELECT url, kind, status_code, url_count, error_code FROM sitemaps WHERE crawl_id = ? ORDER BY id LIMIT 50",
        (crawl_id,),
    )]
    return {
        "job": job,
        "project": project,
        "settings": settings,
        "snap": snapshot,
        "groups": groups,
        "detailed": detailed,
        "severity_counts": issues_repo.counts_by_severity(conn, crawl_id),
        "categories": issues_repo.counts_by_category(conn, crawl_id),
        "category_scores": breakdown.get("categories", {}),
        "reasons": reasons,
        "index_reasons": index_reasons,
        "sitemaps": sitemaps,
    }


def render_report(conn: sqlite3.Connection, crawl_id: int, language: str = "tr") -> str:
    t = Translator(language)
    data = collect_report_data(conn, crawl_id)
    template = _env.get_template("report.html")
    return template.render(
        **data,
        t=t,
        lang=t.language,
        logo=_logo_svg(),
        generated_at=utcnow_iso(),
        PRODUCT_NAME=PRODUCT_NAME,
        SLOGAN=SLOGAN,
        PRODUCT_DESCRIPTION=PRODUCT_DESCRIPTION,
        VERSION=__version__,
        SEVERITY_ORDER=("critical", "high", "medium", "low", "info"),
    )


def save_report(conn: sqlite3.Connection, crawl_id: int, reports_dir: Path, language: str = "tr") -> dict[str, Any]:
    html = render_report(conn, crawl_id, language)
    job = crawls_repo.get_job(conn, crawl_id)
    assert job is not None
    stamp = utcnow_iso().replace(":", "").replace("-", "")[:15]
    filename = safe_filename("zerqon-spider", job["project_name"], f"crawl-{crawl_id}", stamp, language, ext="html")
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / filename
    path.write_text(html, encoding="utf-8")
    cur = conn.execute(
        "INSERT INTO reports(project_id, crawl_id, kind, filename, size_bytes, created_at) VALUES (?, ?, 'html', ?, ?, ?)",
        (job["project_id"], crawl_id, filename, path.stat().st_size, utcnow_iso()),
    )
    return {"id": int(cur.lastrowid or 0), "filename": filename, "path": path}
