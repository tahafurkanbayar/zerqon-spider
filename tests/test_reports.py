"""Sağlık puanı, CSV, HTML raporu, karşılaştırma ve yedekleme testleri."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fixtures.site import serve_site
from tests.test_crawler_e2e import run_crawl
from zerqon.analysis.scoring import compute_score, confidence_level, score_from_groups
from zerqon.config import Settings
from zerqon.db.connection import Database
from zerqon.db.repositories import crawls_repo
from zerqon.reports.backup import BackupError, create_backup, read_manifest, restore_backup
from zerqon.reports.compare import CompareError, compare_crawls
from zerqon.reports.csv_export import EXPORT_KEYS, export_rows, rows_to_csv, safe_cell, safe_filename
from zerqon.reports.html_report import render_report, save_report


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with serve_site() as base:
        yield base


# ------------------------------------------------------------------ puan
def test_score_formula_matches_documentation() -> None:
    score, cats = score_from_groups([("http", "critical", 10, False)], analyzed=100)
    assert score == 92.1
    score, _ = score_from_groups([("http", "critical", 10, False), ("description", "medium", 100, False)], 100)
    assert score == 87.5
    assert score_from_groups([], 100)[0] == 100.0
    assert score_from_groups([("x", "info", 100, False)], 100)[0] == 100.0


def test_score_is_bounded_and_deterministic() -> None:
    groups = [("c", "critical", 100, False)] * 50 + [("s", "high", 0, True)] * 20
    first = score_from_groups(groups, 100)
    assert first == score_from_groups(list(groups), 100)
    assert 0 <= first[0] <= 100
    # Daha fazla etkilenen sayfa daha düşük puan
    assert score_from_groups([("c", "high", 50, False)], 100)[0] < score_from_groups([("c", "high", 5, False)], 100)[0]


def test_confidence_levels() -> None:
    assert confidence_level([]) == "high"
    assert confidence_level(["url_limit"]) == "medium"
    assert confidence_level(["partial_crawl"]) == "medium"
    assert confidence_level(["partial_crawl", "url_limit"]) == "low"
    assert confidence_level(["no_html"]) == "low"


def test_crawl_score_and_confidence(db: Database, settings: Settings, site: str) -> None:
    crawl_id, _, _ = run_crawl(db, settings, site, check_images=True)
    with db.session() as conn:
        snap = crawls_repo.get_snapshot(conn, crawl_id)
        again = compute_score(conn, crawl_id)
    assert snap is not None
    assert 0 < snap["health_score"] < 100
    assert snap["health_score"] == again.score  # deterministik
    assert snap["score_confidence"] in ("high", "medium")

    limited, _, _ = run_crawl(db, settings, site, max_urls=2, use_sitemaps=False, check_images=False)
    with db.session() as conn:
        snap = crawls_repo.get_snapshot(conn, limited)
    assert snap is not None and snap["score_confidence"] == "low"
    assert "url_limit" in snap["confidence_reasons"]


# ------------------------------------------------------------------ CSV
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=SUM(A1)", "'=SUM(A1)"),
        ("+cmd", "'+cmd"),
        ("-2+3", "'-2+3"),
        ("@SUM", "'@SUM"),
        ("\tx", "'\tx"),
        ("-12", "-12"),
        ("normal", "normal"),
        (None, ""),
        (42, 42),
    ],
)
def test_csv_formula_injection_guard(value: object, expected: object) -> None:
    assert safe_cell(value) == expected


def test_csv_turkish_and_bom() -> None:
    text = "".join(rows_to_csv(["başlık", "açıklama"], [["Çağrı İşığı", "=1+1"], ["ğüşöç", None]]))
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows == [["başlık", "açıklama"], ["Çağrı İşığı", "'=1+1"], ["ğüşöç", ""]]


def test_csv_exports_contain_crawl_data(db: Database, settings: Settings, site: str) -> None:
    crawl_id, _, _ = run_crawl(db, settings, site, use_sitemaps=False, check_images=True)
    with db.session() as conn:
        for key in EXPORT_KEYS:
            header, rows = export_rows(conn, crawl_id, key)
            data = list(rows)
            assert header, key
            assert data, key
        header, rows = export_rows(conn, crawl_id, "meta")
        text = "".join(rows_to_csv(header, rows))
    assert "'=HYPERLINK" in text  # sitedeki formül benzeri açıklama etkisizleştirildi
    assert "Hakkımızda | Örnek Site" in text


def test_safe_filename() -> None:
    assert safe_filename("Örnek Şirket", "../../etc/passwd", ext="csv") == "ornek-sirket_etc-passwd.csv"
    assert safe_filename("", ext="html") == "export.html"


# ------------------------------------------------------------------ HTML raporu
def test_html_report_is_self_contained_and_escaped(db: Database, settings: Settings, site: str, tmp_path: Path) -> None:
    crawl_id, _, _ = run_crawl(db, settings, site, check_images=True)
    with db.session() as conn:
        html = render_report(conn, crawl_id, "tr")
        saved = save_report(conn, crawl_id, tmp_path, "en")
        stored = conn.execute("SELECT * FROM reports WHERE id = ?", (saved["id"],)).fetchone()
    # Marka, puan, bölümler
    for text in ("Zerqon", "Crawl Deeper. Discover More.", "Teknik SEO Denetim Raporu", "Tarama sınırlamaları",
                 "Google", "Kırık iç bağlantı", "Önerilen çözüm"):
        assert text in html, text
    # Harici kaynak yok: script yok, dış stylesheet/font/img yok
    assert "<script" not in html.lower()
    assert not re.search(r"<link[^>]+href=", html, re.I)
    assert not re.search(r"""(src|href)=["']https?://(?!127\.0\.0\.1)""", html)
    assert "@import" not in html and "url(http" not in html
    # Siteden gelen XSS denemesi escape edilmiş
    assert "<script>alert('xss-title')</script>" not in html
    assert "onerror=alert" not in html or "&lt;img" in html
    # Kaydedilen dosya
    assert stored is not None and stored["kind"] == "html"
    assert (tmp_path / saved["filename"]).read_text(encoding="utf-8").startswith("<!doctype html>")
    assert "Technical SEO Audit Report" in (tmp_path / saved["filename"]).read_text(encoding="utf-8")


# ------------------------------------------------------------------ karşılaştırma
def test_compare_two_crawls(db: Database, settings: Settings, site: str) -> None:
    a, _, _ = run_crawl(db, settings, site, max_urls=8, use_sitemaps=False, check_images=False)
    with db.session() as conn:
        project_id = crawls_repo.get_job(conn, a)["project_id"]  # type: ignore[index]
        from zerqon.db.repositories import settings_repo
        from zerqon.schemas import CrawlSettingsModel

        b = crawls_repo.create_job(
            conn, project_id, site + "/",
            CrawlSettingsModel(allow_localhost=True, delay_ms=0, max_urls=200, use_sitemaps=True, check_images=False),
        )
        settings_b = settings_repo.get_settings(conn, crawls_repo.get_job(conn, b)["settings_id"])  # type: ignore[index]

    import asyncio
    import threading

    from zerqon.analysis.finalize import finalize_crawl
    from zerqon.analysis.runner import PageAnalysisRunner
    from zerqon.crawler.engine import CrawlEngine, CrawlStats

    asyncio.run(CrawlEngine(db, b, site + "/", settings_b, settings, threading.Event(), CrawlStats(),
                            analyzer=PageAnalysisRunner(), finalizer=finalize_crawl).run())
    with db.session() as conn:
        result = compare_crawls(conn, b, a)  # sıra fark etmez; A eski olur
        assert result.a["id"] == a and result.b["id"] == b
        assert result.urls_new_total > 0
        assert any(u.endswith("/orphan") for u in result.urls_new)
        assert "scope_changed" in result.warnings and "limit_a" in result.warnings
        assert any(name == "max_urls" for name, _, _ in result.settings_diff)
        assert result.issues_new  # yeni keşfedilen sayfaların sorunları
        assert result.score_delta is not None
        with pytest.raises(CompareError):
            compare_crawls(conn, a, a)


# ------------------------------------------------------------------ yedekleme
def test_backup_and_restore_roundtrip(db: Database, settings: Settings, site: str, tmp_path: Path) -> None:
    crawl_id, _, _ = run_crawl(db, settings, site, max_urls=5, use_sitemaps=False, check_images=False)
    backup = create_backup(db, tmp_path)
    manifest = read_manifest(backup)
    assert manifest["counts"]["crawl_jobs"] >= 1 and manifest["schema_version"] >= 2

    with db.session() as conn:
        conn.execute("DELETE FROM projects")
        assert conn.execute("SELECT COUNT(*) FROM crawl_jobs").fetchone()[0] == 0

    restore_backup(db, backup, tmp_path)
    with db.session() as conn:
        assert crawls_repo.get_job(conn, crawl_id) is not None
        assert conn.execute("SELECT COUNT(*) FROM pages WHERE crawl_id = ?", (crawl_id,)).fetchone()[0] == 5
    assert any(p.name.startswith("pre-restore") for p in tmp_path.glob("*.zip"))


def test_restore_rejects_invalid_archives(db: Database, tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../../evil.txt", "x")
    with pytest.raises(BackupError):
        restore_backup(db, bad)
    not_zip = tmp_path / "x.zip"
    not_zip.write_text("not a zip")
    with pytest.raises(BackupError):
        restore_backup(db, not_zip)
    fake = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake, "w") as archive:
        archive.writestr("zerqon.db", b"garbage")
        archive.writestr("manifest.json", '{"product": "Zerqon Spider", "schema_version": 1}')
    with pytest.raises(BackupError):
        restore_backup(db, fake)
