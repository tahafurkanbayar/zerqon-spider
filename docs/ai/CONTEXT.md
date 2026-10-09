# Hızlı Bağlam (Yeni Oturum İçin İlk Okunacak Dosya)

> Amaç: Yeni bir AI oturumunun 1 dakikada kaldığı yerden devam edebilmesi.
> Bu dosya **her aşama sonunda** güncellenir. Ayrıntı için: `ROADMAP.md` (ne kaldı), `PROGRESS.md` (ne yapıldı), `DECISIONS.md` (neden), `PROMPT.md` (orijinal gereksinim).

## Kimlik
- Ürün: **Zerqon Spider** — "Crawl Deeper. Discover More." — Advanced SEO Crawler & Auditor
- Repo: https://github.com/tahafurkanbayar/zerqon-spider (public)
- Commit yazarı: Taha Furkan Bayar <tahafurkanbayar@gmail.com> (repo-yerel git config)
- Dil: Arayüz/doküman Türkçe (varsayılan), İngilizce destekli. Kod/identifier İngilizce.

## Geliştirme ortamı (Windows 10, Git Bash + PowerShell)
- Sistem Python'u 3.15 → kullanılmaz. `.venv` = uv ile kurulu CPython **3.12.15**.
- Komutlar (repo kökünden):
  - Test: `.venv/Scripts/python -m pytest -q`
  - Sunucu: `.venv/Scripts/python -m zerqon` veya `python run.py`
  - Bağımlılık ekleme: `uv pip install --python .venv <pkg>` → `requirements.txt` güncelle
- Chromium: `.venv/Scripts/python -m playwright install chromium` (kurulu)

## Mevcut durum
- **Aktif aşama:** Aşama 5 — Raporlama ve geçmiş
- **Son tamamlanan:** Aşama 4 (tarama ekranları, URL tablosu/detay, sorunlar, CSV)
- **Sıradaki adım:** analysis/scoring.py + docs/SCORING.md, reports/html_report.py, /crawls/{id}/reports, compare.py + /compare, reports/backup.py + ayarlar sayfası

## Kod haritası (özet)
Bkz. `DECISIONS.md` ADR-001. Giriş noktaları:
- `run.py` → bootstrap (venv, deps, chromium) → `python -m zerqon`
- `zerqon/__main__.py` → migration + uvicorn
- `zerqon/web/app.py::create_app()`
- `zerqon/crawler/manager.py::CrawlManager` → `engine.py::CrawlEngine`
- `zerqon/analysis/runner.py` → page checks (canlı) + site checks (tarama sonu)

## Konvansiyonlar
- SQL her zaman parametrik; sıralama sütunları beyaz listeden.
- UI metinleri yalnızca `zerqon/i18n/locales/*.json`; şablonda `{{ t('key') }}`.
- Yeni SEO kontrolü: `analysis/checks/*.py` içinde `@page_check` / `@site_check` + `analysis/issues.py` tanımı + iki locale'de `issues.<code>.{name,desc,fix}`.
- Belirsiz sonuçlar "aday"/"olası" diliyle sunulur (yetim sayfa adayı, benzer içerik adayı).
