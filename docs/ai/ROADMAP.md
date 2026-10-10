# Yol Haritası ve Kapsam Takibi

> Kaynak: `PROMPT.md` §22 (geliştirme sırası) + §23 (kabul kriterleri).
> Durum işaretleri: `[ ]` yapılmadı · `[~]` kısmi · `[x]` tamam ve test edildi.
> Her madde tamamlandığında `PROGRESS.md`'ye commit referansıyla kayıt düşülür.

## Aşama 1 — Temel altyapı
- [x] Proje yapısı, `pyproject.toml`, `requirements.txt` (sabit sürümler)
- [x] `.gitignore`, `.env.example`, `CLAUDE.md`
- [x] Yapılandırma (`zerqon/config.py`) + veri dizini
- [x] Loglama (dönen dosya, maskeleme)
- [x] SQLite bağlantısı (WAL) + sürümlü migration + başlangıç şeması
- [x] i18n altyapısı (tr varsayılan, en)
- [x] FastAPI uygulaması, güvenlik middleware'leri
- [x] HTMX temel arayüz iskeleti, marka (logo, favicon, tema)
- [x] `run.py` tek komutla başlatma

## Aşama 2 — Tarama motoru
- [x] URL normalizasyonu / `url_key`
- [x] Kapsam (alan adı, alt alan, include/exclude)
- [x] SSRF koruması + localhost modu
- [x] robots.txt (RFC 9309 + joker)
- [x] Sitemap + sitemap index + gzip, XXE-güvenli
- [x] Fetcher: async, boyut limiti, retry, 429/503 backoff, hız sınırlayıcı
- [x] Frontier + checkpoint + devam ettirme
- [x] Playwright render (havuz, limit, ana belge fulfill)
- [x] Engine + Manager (thread, stop, interrupted işaretleme)

## Aşama 3 — SEO analizleri
- [x] HTML parser (title, meta, headings, links, images, canonical, hreflang, OG/Twitter, metin)
- [x] Structured data (JSON-LD, Microdata, RDFa)
- [x] Issue registry + page checks (A–M)
- [x] Indexability hesaplayıcı
- [x] Site checks (yinelenenler, kırık linkler, canonical hedefleri, redirect zincirleri, hreflang karşılıklılık, yetim aday, sitemap tutarlılığı, benzer içerik)
- [x] Önceliklendirme motoru

## Aşama 4 — Yönetim paneli
- [x] Dashboard
- [x] Proje CRUD + ayarlar
- [x] İzin onaylı tarama başlatma
- [x] Gerçek zamanlı ilerleme + durdur/devam
- [x] URL tablosu (sunucu tarafı filtre/sıralama/sayfalama, seçili satır dışa aktarma)
- [x] URL detay sayfası
- [x] Sorunlar ekranı

## Aşama 5 — Raporlama ve geçmiş
- [x] CSV dışa aktarma (10 tür, BOM, formula injection koruması)
- [x] Bağımsız HTML raporu
- [x] Sağlık puanı + güvenilirlik
- [x] Tarama karşılaştırması
- [x] Yedekleme / geri yükleme

## Aşama 6 — Test ve son kontroller
- [x] Birim testleri (§19 listesi)
- [x] Entegrasyon + uçtan uca (yerel test sitesi)
- [x] Güvenlik negatif testleri
- [x] README (Türkçe, §20 başlıkları)
- [x] Temiz klonla kurulum doğrulaması

## Kabul kriterleri (§23)
| # | Kriter | Durum | Kanıt |
|---|---|---|---|
| 1 | Yerelde açılır | [x] | Temiz klonda `python run.py` → HTTP 200 (2026-10-09) |
| 2 | Proje oluşturma | [x] | `test_web_basic::test_create_project_flow` |
| 3 | Tarama ayarları değiştirilebilir | [x] | Proje formu + `test_db::test_project_crud_and_settings_roundtrip` |
| 4 | İzin onayı | [x] | `test_web_e2e::test_crawl_requires_permission`, DB CHECK kısıtı |
| 5 | Gerçek siteyi tarama | [~] | Gerçek HTTP ile yerel test sitesi taranıyor; üçüncü taraf canlı site izin olmadığı için taranmadı — kullanıcı kendi sitesinde doğrulamalı |
| 6 | robots/kapsam uyumu | [x] | `test_crawler_e2e` (robots engeli, nofollow, dış alan, exclude, max_urls/derinlik), `test_robots_sitemap` |
| 7 | HTML + render DOM analizi | [x] | `test_render` (JavaScript + hibrit, Chromium) |
| 8 | İlerleme takibi | [x] | `/crawls/{id}/progress` HTMX; ekran görüntüsüyle doğrulandı |
| 9 | Gerçek veriden sorunlar | [x] | `test_crawler_e2e::test_issues_and_prioritization` |
| 10 | Kanıt + çözüm önerisi | [x] | Sorunlar ekranı, URL detayı, HTML rapor; `test_every_issue_has_translations` |
| 11 | URL detayları | [x] | `test_web_e2e::test_full_ui_flow` (tüm URL detay sayfaları 200) |
| 12 | CSV + HTML rapor | [x] | `test_reports`, `test_web_e2e::test_reports_compare_and_backup_routes` |
| 13 | Eski taramalar korunur | [x] | `test_web_e2e::test_second_crawl_keeps_history` |
| 14 | İki tarama karşılaştırma | [x] | `test_reports::test_compare_two_crawls`, `/compare` |
| 15 | Güvenlik önlemleri | [x] | `test_security` (SSRF), CSRF/Host/XSS/SQLi/yol enjeksiyonu testleri |
| 16 | Testler çalıştırıldı | [x] | 148/148 geçti |
| 17 | README eksiksiz | [x] | README.md (§20 başlıklarının tamamı) |

## Sürüm planı
| Sürüm | Durum | Kapsam |
|---|---|---|
| v1.0.0 | Yayımlandı (2026-10-10) | Aşama 1–6, §23 kabul kriterleri |
| v1.1.0 | Yayımlandı (2026-10-10) | Windows masaüstü uygulaması (tek .exe, pywebview + PyInstaller), Chromium'u arayüzden kurma, CI ile exe derleme |
| v1.2.0 | Planlanıyor | Kullanıcı geri bildirimine göre (adaylar: URL listesi içe aktarma, GSC entegrasyonu, kimlik doğrulamalı tarama, tam ISO hreflang tablosu, kurulum sihirbazı/otomatik güncelleme) |
| Gelecek | Fikir | macOS / Linux paketleri, web (sunucu) sürümü — kullanıcı belirtti |
