# İlerleme Günlüğü

> En yeni kayıt en üstte. Her kayıt: tarih · aşama · özet · test durumu · commit.

---

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
