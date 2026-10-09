"""Uçtan uca başarılı senaryo: arayüz üzerinden proje → izinli tarama → sonuç ekranları → dışa aktarma."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.site import serve_site
from zerqon.reports.csv_export import EXPORT_KEYS


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with serve_site() as base:
        yield base


def create_project(client: TestClient, site: str, **extra: str) -> int:
    data = {
        "name": "Yerel Test Sitesi", "start_url": site + "/", "max_urls": "200", "max_depth": "10",
        "concurrency": "4", "delay_ms": "0", "timeout_seconds": "10", "max_retries": "1",
        "user_agent": "ZerqonSpider-Test/1.0", "render_mode": "standard", "max_render_pages": "10",
        "use_sitemaps": "on", "check_images": "on", "allow_localhost": "on",
        "title_min_chars": "30", "title_max_chars": "60", "description_min_chars": "70",
        "description_max_chars": "160", "min_word_count": "200", "max_url_length": "115",
        "large_image_bytes": "204800", "deep_page_depth": "4",
    }
    data.update(extra)
    res = client.post("/projects/new", data=data, follow_redirects=False)
    assert res.status_code == 303, res.text[:500]
    return int(re.search(r"/projects/(\d+)", res.headers["location"]).group(1))  # type: ignore[union-attr]


def run_crawl_via_ui(client: TestClient, project_id: int) -> int:
    res = client.post(f"/projects/{project_id}/crawl", data={"permission_confirmed": "on"}, follow_redirects=False)
    assert res.status_code == 303
    crawl_id = int(res.headers["location"].rsplit("/", 1)[1])
    client.app.state.manager.wait(crawl_id, timeout=60)  # type: ignore[attr-defined]
    return crawl_id


def test_crawl_requires_permission(client: TestClient, site: str) -> None:
    pid = create_project(client, site)
    page = client.get(f"/projects/{pid}/crawl")
    assert page.status_code == 200
    assert 'name="permission_confirmed"' in page.text
    res = client.post(f"/projects/{pid}/crawl", data={}, follow_redirects=False)
    assert res.status_code == 303
    assert "error=permission_required" in res.headers["location"]
    assert "crawl" not in client.get(f"/projects/{pid}").text.split("Tarama geçmişi")[1][:20]


def test_full_ui_flow(client: TestClient, site: str) -> None:
    pid = create_project(client, site)
    crawl_id = run_crawl_via_ui(client, pid)

    overview = client.get(f"/crawls/{crawl_id}")
    assert overview.status_code == 200
    assert "Tamamlandı" in overview.text
    assert "Kırık iç bağlantı" in overview.text or "Yönlendirme döngüsü" in overview.text

    # İlerleme uç noktası bitmiş taramada sayfayı yeniletir
    progress = client.get(f"/crawls/{crawl_id}/progress", headers={"HX-Request": "true"})
    assert progress.headers.get("HX-Refresh") == "true"

    # URL tablosu: tam sayfa + HTMX parçası + filtre + sıralama + sayfalama
    table = client.get(f"/crawls/{crawl_id}/pages")
    assert table.status_code == 200 and "pages-table" in table.text
    partial = client.get(
        f"/crawls/{crawl_id}/pages?status=4xx&sort=url&dir=desc",
        headers={"HX-Request": "true", "HX-Target": "pages-table"},
    )
    assert partial.status_code == 200
    assert "/broken" in partial.text and "<html" not in partial.text
    assert "/about" not in partial.text
    search = client.get(f"/crawls/{crawl_id}/pages?q=hakk", headers={"HX-Request": "true", "HX-Target": "pages-table"})
    assert "/about" in search.text
    paged = client.get(f"/crawls/{crawl_id}/pages?per_page=25&page=2&sort=bogus' OR 1=1--")
    assert paged.status_code == 200  # beyaz liste dışı sıralama güvenle yok sayılır
    issue_filter = client.get(f"/crawls/{crawl_id}/pages?issue=title_too_short")
    assert issue_filter.status_code == 200

    # Her URL'nin detay sayfası açılabilmeli
    ids = sorted(set(re.findall(rf"/crawls/{crawl_id}/pages/(\d+)", table.text)))
    assert len(ids) >= 10
    for page_id in ids:
        detail = client.get(f"/crawls/{crawl_id}/pages/{page_id}")
        assert detail.status_code == 200, page_id
        assert "Indexlenebilirlik analizi" in detail.text

    # Sorunlar ekranı, filtreler ve etkilenen URL parçası
    issues = client.get(f"/crawls/{crawl_id}/issues")
    assert issues.status_code == 200 and "issue-broken_internal_link" in issues.text
    high = client.get(f"/crawls/{crawl_id}/issues?severity=high", headers={"HX-Request": "true", "HX-Target": "issues-list"})
    assert "issue-redirect_loop" in high.text and "issue-title_too_short" not in high.text
    urls = client.get(f"/crawls/{crawl_id}/issues/broken_internal_link")
    assert urls.status_code == 200 and "/broken" in urls.text
    assert client.get(f"/crawls/{crawl_id}/issues/not_a_code").status_code == 404

    # CSV dışa aktarma: tüm türler + seçili satırlar
    for key in EXPORT_KEYS:
        res = client.get(f"/crawls/{crawl_id}/export/{key}.csv")
        assert res.status_code == 200, key
        assert res.text.startswith("﻿")
        assert "attachment" in res.headers["content-disposition"]
    selected = client.post(f"/crawls/{crawl_id}/pages/export", data={"page_id": ids[:3]})
    rows = list(csv.reader(io.StringIO(selected.text.lstrip("﻿"))))
    assert rows[0][0] == "url" and len(rows) == 4

    # Dashboard ve proje sayfası veriyi gösterir
    assert "Yerel Test Sitesi" in client.get("/").text
    assert f"/crawls/{crawl_id}" in client.get(f"/projects/{pid}").text


def test_second_crawl_keeps_history(client: TestClient, site: str) -> None:
    pid = create_project(client, site, max_urls="10")
    first = run_crawl_via_ui(client, pid)
    second = run_crawl_via_ui(client, pid)
    assert first != second
    detail = client.get(f"/projects/{pid}").text
    assert f"#{first}" in detail and f"#{second}" in detail
    assert client.get(f"/crawls/{first}/pages").status_code == 200


def test_reports_compare_and_backup_routes(client: TestClient, site: str) -> None:
    pid = create_project(client, site, max_urls="15")
    first = run_crawl_via_ui(client, pid)
    second = run_crawl_via_ui(client, pid)

    # HTML raporu üret, görüntüle, indir
    assert client.get(f"/crawls/{second}/reports").status_code == 200
    res = client.post(f"/crawls/{second}/reports/html", data={"language": "en"}, follow_redirects=False)
    assert res.status_code == 303 and "report_created" in res.headers["location"]
    page = client.get(f"/crawls/{second}/reports").text
    report_id = re.search(r'href="/reports/(\d+)"', page).group(1)  # type: ignore[union-attr]
    view = client.get(f"/reports/{report_id}")
    assert view.status_code == 200 and "Technical SEO Audit Report" in view.text
    assert "default-src 'none'" in view.headers["content-security-policy"]
    download = client.get(f"/reports/{report_id}?download=1")
    assert "attachment" in download.headers["content-disposition"]
    assert f"/reports/{report_id}" in client.get(f"/projects/{pid}").text

    # Karşılaştırma
    cmp_page = client.get(f"/compare?crawl={first}&crawl={second}")
    assert cmp_page.status_code == 200 and "Tarama karşılaştırması" in cmp_page.text
    assert client.get(f"/compare?a={first}").status_code == 400

    # Yedekleme, indirme, yol enjeksiyonu engeli, geri yükleme
    res = client.post("/settings/backup", follow_redirects=False)
    assert res.status_code == 303
    settings_page = client.get("/settings").text
    name = re.search(r'/settings/backups/(zerqon-backup-[^"]+\.zip)', settings_page).group(1)  # type: ignore[union-attr]
    archive = client.get(f"/settings/backups/{name}")
    assert archive.status_code == 200 and archive.content[:2] == b"PK"
    assert client.get("/settings/backups/..%2F..%2Fzerqon.db").status_code == 404
    assert client.get("/settings/backups/zerqon.db").status_code == 404
    restored = client.post(
        "/settings/restore", files={"file": ("backup.zip", archive.content, "application/zip")}, follow_redirects=False
    )
    assert "restore_done" in restored.headers["location"]
    bad = client.post("/settings/restore", files={"file": ("x.zip", b"nope", "application/zip")}, follow_redirects=False)
    assert "restore_failed" in bad.headers["location"]
    assert client.get(f"/crawls/{second}").status_code == 200
