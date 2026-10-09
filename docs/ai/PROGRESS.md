# İlerleme Günlüğü

> En yeni kayıt en üstte. Her kayıt: tarih · aşama · özet · test durumu · commit.

---

## 2026-10-09 — Aşama 3 tamamlandı: SEO analizleri
- `analysis/issues.py`: 100+ sorun kodu (kategori, temel önem, page/site kapsamı). Metinler `i18n/locales/{tr,en}.issues-{a,b}.json` (i18n artık `<dil>.*.json` parçalarını birleştiriyor).
- `analysis/checks/page_checks.py`: HTTP/URL, title, description, heading, canonical, robots direktifleri, görseller, bağlantılar, içerik, render farkları, yapılandırılmış veri, OG/Twitter, hreflang.
- Site kontrolleri: `site_links.py` (redirect zincir/döngü/hata, kırık iç bağlantı, URL varyasyonları, HTTP/HTTPS yinelenmesi, derin sayfa, yetim aday), `site_content.py` (yinelenen title/description/H1, birebir/benzer içerik SimHash+LSH, canonical hedefleri, bağlamsal canonical eksikliği, görsel kaynakları), `site_sitemap.py` (robots/sitemap, sitemap URL tutarlılığı, hreflang karşılıklılık).
- `indexability.py` (crawlable / teknik indexlenebilir / gerçek indeks ayrımı), `prioritization.py` (yaygınlık, sayfa önemi, indexlenemez bağlam, şablon geneli kuralları), `finalize.py` hattı.
- `lang_codes.py`: hreflang BCP 47 biçim doğrulaması + yaygın hata listesi (tam ISO tablosu yerine; bkz. Bilinen eksikler).
- Not: Uzun ISO kod listesi yazımı API içerik filtresine takıldı; çözüm olarak biçim tabanlı doğrulamaya geçildi.
- Testler: 124/124 geçti.

## 2026-10-09 — Aşama 2 tamamlandı: Tarama motoru
- `crawler/`: urls (normalizasyon/url_key/varyasyon imzası), scope, security (IP politikası + bağlantı anında doğrulayan httpcore backend), robots (RFC 9309 + joker + en uzun eşleşme), sitemap (index/gzip/text, XXE ve zip-bombası korumalı), fetcher (akışlı okuma + boyut sınırı, retry, 429/503 uyarlamalı geri çekilme, Retry-After), frontier (BFS, max_urls asla aşılmaz, ertelenmiş sitemap), renderer (Playwright, ana belge fulfill, SSRF route filtresi), store (toplu, atomik flush), engine, manager (thread başına tarama, stop/resume), postprocess (inlink, tık derinliği, redirect zincir/döngü, in_sitemap).
- `parsing/`: lxml tabanlı tek geçiş parser (title, meta, robots, canonical, headings, links, images, hreflang, OG/Twitter, JSON-LD/Microdata/RDFa, görünür metin, SHA-1 + SimHash).
- Migration `0002_crawl_events.sql` (kullanıcıya gösterilecek tarama olayları).
- Yerel test sitesi `tests/fixtures/site.py` (uvicorn, gerçek HTTP).
- Testler: 76/76 geçti (URL/scope, robots/sitemap, SSRF negatif testleri, e2e tarama, limitler, stop/resume, 429, Playwright JS+hibrit render).

## 2026-10-09 — Aşama 1 tamamlandı: Temel altyapı
- Paket iskeleti `zerqon/` (config, logging, i18n, db, schemas, web).
- SQLite: WAL + FK, sürümlü migration (`0001_initial.sql`, 20 tablo), repository'ler (settings, projects, crawls, stats).
- FastAPI: TrustedHost, aynı-köken (CSRF) kontrolü, CSP/güvenlik başlıkları, dostça hata sayfaları (disk dolu, DB kilitli).
- Arayüz: marka (Z + geometrik örümcek SVG logo, favicon), açık/koyu/sistem tema, TR/EN, karşılama ekranı, dashboard, proje CRUD + tarama ayarları formu.
- `run.py` (venv + deps + Chromium + başlat, damga dosyaları ile tekrar kurulum yok), `python -m zerqon`.
- Testler: 17/17 geçti (`tests/test_db.py`, `test_i18n.py`, `test_web_basic.py`).

## 2026-10-09 — Başlangıç
- Prompt alındı, `docs/ai/` hafıza yapısı kuruldu (PROMPT, CONTEXT, ROADMAP, DECISIONS, PROGRESS).
- Ortam: uv ile CPython 3.12.15, `.venv`; bağımlılıklar kuruldu; Playwright Chromium indirildi.
- Mimari kararlar ADR-001…ADR-016 olarak yazıldı.
