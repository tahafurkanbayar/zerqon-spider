# Mimari Karar Kayıtları (ADR)

> Format: `ADR-NNN — Başlık` · Durum · Bağlam · Karar · Sonuç.
> Yeni karar eklerken numarayı artır; eski kararı değiştirme, "Yerine geçen: ADR-x" notu düş.

---

## ADR-001 — Paket düzeni ve katmanlar
**Durum:** Kabul · 2026-10-09
**Karar:** Tek Python paketi `zerqon/`, alt paketler sorumluluklara göre ayrılır:

| Katman | Paket | Not |
|---|---|---|
| Yapılandırma | `zerqon/config.py` | pydantic-settings, `.env` |
| Loglama | `zerqon/logging_config.py` | Dönen dosya log'u, gizli veri maskeleme |
| i18n | `zerqon/i18n/` | `locales/tr.json`, `locales/en.json` |
| Veritabanı | `zerqon/db/` | sqlite3, migration, repository modülleri |
| Şemalar | `zerqon/schemas.py` | Pydantic giriş/çıkış modelleri |
| Tarama | `zerqon/crawler/` | urls, scope, security, robots, sitemap, fetcher, renderer, frontier, engine, manager |
| Ayrıştırma | `zerqon/parsing/` | lxml tabanlı HTML parser, structured data |
| Analiz | `zerqon/analysis/` | issue registry, page checks, site checks, indexability, prioritization, scoring |
| Raporlama | `zerqon/reports/` | csv, html, compare, backup |
| Web | `zerqon/web/` | FastAPI app, routes, Jinja2 şablonları, static |

**Sonuç:** Yeni SEO kontrolü = `zerqon/analysis/checks/` altına dekoratörlü bir fonksiyon + `issues` registry'ye tanım + locale metinleri. Başka hiçbir yer değişmez.

## ADR-002 — ORM yok, sqlite3 + repository
**Durum:** Kabul
**Bağlam:** Toplu yazma performansı ve şeffaf SQL isteniyor; ek ana bağımlılık istenmiyor.
**Karar:** Standart `sqlite3`, her zaman parametrik sorgu. WAL, `foreign_keys=ON`, `synchronous=NORMAL`, `busy_timeout=5000`. Migration'lar `zerqon/db/migrations/NNNN_*.sql`, `schema_migrations` tablosunda sürüm takibi.
Sıralama için kullanıcıdan gelen sütun adı **beyaz liste** ile eşlenir (SQL'e asla doğrudan girmez).

## ADR-003 — Tarama kendi thread'inde, kendi event loop'unda
**Durum:** Kabul
**Bağlam:** Tarama UI'ı engellememeli; SQLite yazmaları senkron.
**Karar:** `CrawlManager` her tarama için ayrı bir `threading.Thread` başlatır; thread içinde `asyncio.run(engine.run())`. Durdurma `threading.Event` ile. İlerleme bellekteki `CrawlStats` + DB `crawl_jobs` satırı (heartbeat) üzerinden okunur. Uygulama açılışında `running` kalmış işler `interrupted` olarak işaretlenir.

## ADR-004 — Checkpoint = `frontier` tablosu
**Durum:** Kabul
**Karar:** Keşfedilen her URL `frontier(crawl_id, url_key UNIQUE)` satırıdır (`pending/done/skipped`). Kuyruk bellekte, kalıcılık DB'de (toplu flush). Devam ettirmede `pending` satırlar yeniden kuyruğa alınır, tüm `url_key`'ler "görüldü" kümesine yüklenir.

## ADR-005 — Yönlendirmeler otomatik takip edilmez
**Durum:** Kabul
**Karar:** Fetcher redirect takip etmez. 3xx yanıt kendi `pages` satırı olur, hedef URL kapsam/robots/SSRF kontrolünden geçerek frontier'a eklenir. Zincirler ve döngüler tarama sonrası sayfa grafiğinden çıkarılır (`redirects` tablosu). Böylece her hop limit, kapsam ve güvenlik kurallarına tabidir.

## ADR-006 — SSRF koruması bağlantı anında
**Durum:** Kabul
**Bağlam:** Ön DNS kontrolü DNS-rebinding'e açıktır.
**Karar:** httpcore için özel `AsyncNetworkBackend`: hostname'i çözer, tüm IP'leri politika ile doğrular, **doğrulanmış IP'ye** bağlanır (TLS SNI hostname ile kalır). Ek olarak istek öncesi hızlı kontrol (anlaşılır hata). Playwright'ta `page.route` ile her alt istek aynı politikadan geçer. `trust_env=False` (proxy ile atlatmayı önler).
Engellenen: loopback, RFC1918, link-local, CGNAT, multicast, reserved, unspecified, bulut metadata (169.254.169.254, fd00:ec2::254 vb.).
**Localhost modu:** `.env`'de `ZERQON_ALLOW_LOCALHOST=true` **ve** tarama ayarında "localhost'a izin ver" seçili olmalı. Yalnızca loopback açılır; özel ağ/metadata yine kapalı.

## ADR-007 — robots.txt kendi parser'ımız
**Durum:** Kabul
**Bağlam:** `urllib.robotparser` joker (`*`, `$`) ve en-uzun-eşleşme kuralını desteklemez.
**Karar:** RFC 9309 + Google davranışı: en spesifik user-agent grubu, en uzun eşleşen kural, eşitlikte `Allow` kazanır. 4xx → kısıt yok; 5xx/ağ hatası → tamamen engelli (temkinli). `Crawl-delay` yapılandırılan gecikmeden büyükse (üst sınır 30 sn) uygulanır.

## ADR-008 — Kapsam kuralı
**Durum:** Kabul
**Karar:** Başlangıç host'unun `www.` öneki atılmış hali "site tabanı"dır. `taban` ve `www.taban` dahili; alt alan adları yalnızca ayar açıksa. http/https aynı site sayılır (tutarsızlık ayrıca raporlanır). Dahil/hariç kuralları regex (güvenli derleme + uzunluk sınırı). Kapsam dışı URL'ler kaydedilir ama **asla** getirilmez (harici bağlantı durum kontrolü yapılmaz — v1 kararı).

## ADR-009 — URL normalizasyonu: `url_key`
**Durum:** Kabul
**Karar:** Tekilleştirme anahtarı: şema/host küçük harf, varsayılan port atılır, fragment atılır, yüzde-kodlama normalize, boş path → `/`, nokta segmentleri çözülür. Sorgu parametre **sırası korunur** (sıralamak farklı URL'leri birleştirebilir). Orijinal URL ayrıca saklanır; büyük/küçük harf, sondaki `/` ve parametre varyasyonları "yinelenen URL varyasyonu" olarak raporlanır.

## ADR-010 — Render: ana belge yeniden indirilmez
**Durum:** Kabul
**Karar:** Playwright'ta ana belge isteği, HTTP aşamasında alınan ham yanıtla `route.fulfill` edilir (sunucuya ikinci yük yok, ham/render karşılaştırması aynı kaynağa dayanır). Görsel/medya/font istekleri bloklanır. Tek browser, sınırlı sayıda context (semafor), sayfa başına zaman aşımı, toplam render limiti.
Hibrit modda render tetikleyicileri: düşük ham kelime sayısı, boş SPA kökü (`#root`, `#app`, `#__next`, `#__nuxt`), `<noscript>` uyarıları, yoğun script/az metin oranı.

## ADR-011 — Sorun modeli ve önceliklendirme
**Durum:** Kabul
**Karar:** Sorun tanımları (`IssueDef`) kodda registry; ad/açıklama/çözüm metinleri locale dosyalarında (`issues.<code>.*`). DB'de `issues` satırı: code, category, base_severity, severity, priority_score, evidence, signals. Önceliklendirme tarama sonunda: yaygınlık (etkilenen oran), indexlenebilirlik bağlamı, sayfa önemi (inlink, sitemap'te olma) ile seviye yükseltme/düşürme. Kurallar `analysis/prioritization.py`'de ve `docs/SCORING.md`'de belgelenir.

## ADR-012 — Sağlık puanı
**Durum:** Kabul
**Karar:** Deterministik çarpımsal model: `score = 100 × Π(1 − w_sev × √ratio_code)`; `w = {critical:.25, high:.12, medium:.05, low:.015, info:0}`. Güvenilirlik (high/medium/low) ayrı hesaplanır: tamamlanma durumu, URL limitine takılma, taranan sayfa sayısı, hata oranı, robots engeli oranı. "Google'ın resmi puanı değildir" uyarısı her gösterimde.

## ADR-013 — Benzer içerik: SimHash + LSH bantları
**Durum:** Kabul
**Karar:** Görünür metin 3-kelime shingle → 64-bit SimHash. 4×16-bit bantta eşleşen adaylar Hamming ≤ 3 ise "benzer içerik adayı". Birebir aynı içerik: normalize metin SHA-1. O(n²) karşılaştırmadan kaçınılır.

## ADR-014 — Yerel web güvenliği
**Durum:** Kabul
**Karar:** Sunucu varsayılan `127.0.0.1`. `TrustedHostMiddleware` (DNS rebinding'e karşı). Durum değiştiren isteklerde (POST/PUT/DELETE) `Origin`/`Referer` aynı-köken kontrolü (yerel CSRF'e karşı). Jinja2 autoescape açık; hedef siteden gelen hiçbir HTML ham basılmaz. Güvenlik başlıkları (CSP `default-src 'self'`, `X-Frame-Options: DENY`, `nosniff`).

## ADR-015 — Ön yüz bağımlılıkları yerelde
**Durum:** Kabul
**Karar:** HTMX `zerqon/web/static/vendor/` altına sabitlenmiş sürümle konur; CDN yok, font yok (sistem font yığını). Grafikler sunucuda üretilen SVG/CSS. HTML raporu tamamen tek dosya (inline CSS + inline SVG logo, JS yok/inline).

## ADR-016 — Python sürümü
**Durum:** Kabul
**Bağlam:** Geliştirme makinesinde sistem Python'u 3.15; prompt 3.12 istiyor.
**Karar:** Hedef 3.12 (3.13 de desteklenir). `run.py` uygun yorumlayıcıyı bulur (mevcut yorumlayıcı → `py -3.12` → `python3.12` → `uv python find 3.12`), `.venv`'i onunla kurar. Geliştirmede `.venv` uv ile yönetilen CPython 3.12 ile oluşturuldu.
