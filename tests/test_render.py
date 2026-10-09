"""Playwright JavaScript render testleri (Chromium kurulu değilse atlanır)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from zerqon.config import Settings
from zerqon.db.connection import Database
from tests.fixtures.site import serve_site
from tests.test_crawler_e2e import pages_by_path, run_crawl


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = [
    pytest.mark.playwright,
    pytest.mark.skipif(not _chromium_available(), reason="Playwright Chromium kurulu değil"),
]


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with serve_site() as base:
        yield base


@pytest.mark.parametrize("mode", ["javascript", "hybrid"])
def test_js_rendering_discovers_dom_content(db: Database, settings: Settings, site: str, mode: str) -> None:
    crawl_id, status, stats = run_crawl(
        db, settings, site, render_mode=mode, use_sitemaps=False, check_images=False, max_render_pages=50
    )
    assert status == "completed"
    with db.session() as conn:
        pages = pages_by_path(conn, crawl_id, site)
        js = pages["/js-page"]
        meta = conn.execute("SELECT * FROM page_metadata WHERE page_id = ?", (js["id"],)).fetchone()
        events = [r["code"] for r in conn.execute("SELECT code FROM crawl_events WHERE crawl_id = ?", (crawl_id,))]
    assert "render_unavailable" not in events
    assert js["rendered"] == 1
    assert js["render_reason"] == ("javascript_mode" if mode == "javascript" else "spa_root")
    assert meta["raw_h1"] is None
    assert meta["rendered_h1"] == "Render edilmiş başlık"
    assert meta["h1"] == "Render edilmiş başlık"
    assert meta["rendered_word_count"] > meta["raw_word_count"]
    assert meta["render_only_links"] == 1
    # Yalnızca render edilmiş DOM'daki bağlantıyla keşfedilen sayfa
    assert "/js-only-link" in pages
    if mode == "hybrid":
        # Hibritte JS gerektirmeyen sayfalar render edilmez
        assert pages["/about"]["rendered"] == 0
