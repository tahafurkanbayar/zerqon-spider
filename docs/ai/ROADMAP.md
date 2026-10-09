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
- [ ] URL normalizasyonu / `url_key`
- [ ] Kapsam (alan adı, alt alan, include/exclude)
- [ ] SSRF koruması + localhost modu
- [ ] robots.txt (RFC 9309 + joker)
- [ ] Sitemap + sitemap index + gzip, XXE-güvenli
- [ ] Fetcher: async, boyut limiti, retry, 429/503 backoff, hız sınırlayıcı
- [ ] Frontier + checkpoint + devam ettirme
- [ ] Playwright render (havuz, limit, ana belge fulfill)
- [ ] Engine + Manager (thread, stop, interrupted işaretleme)

## Aşama 3 — SEO analizleri
- [ ] HTML parser (title, meta, headings, links, images, canonical, hreflang, OG/Twitter, metin)
- [ ] Structured data (JSON-LD, Microdata, RDFa)
- [ ] Issue registry + page checks (A–M)
- [ ] Indexability hesaplayıcı
- [ ] Site checks (yinelenenler, kırık linkler, canonical hedefleri, redirect zincirleri, hreflang karşılıklılık, yetim aday, sitemap tutarlılığı, benzer içerik)
- [ ] Önceliklendirme motoru

## Aşama 4 — Yönetim paneli
- [ ] Dashboard
- [ ] Proje CRUD + ayarlar
- [ ] İzin onaylı tarama başlatma
- [ ] Gerçek zamanlı ilerleme + durdur/devam
- [ ] URL tablosu (sunucu tarafı filtre/sıralama/sayfalama, seçili satır dışa aktarma)
- [ ] URL detay sayfası
- [ ] Sorunlar ekranı

## Aşama 5 — Raporlama ve geçmiş
- [ ] CSV dışa aktarma (10 tür, BOM, formula injection koruması)
- [ ] Bağımsız HTML raporu
- [ ] Sağlık puanı + güvenilirlik
- [ ] Tarama karşılaştırması
- [ ] Yedekleme / geri yükleme

## Aşama 6 — Test ve son kontroller
- [ ] Birim testleri (§19 listesi)
- [ ] Entegrasyon + uçtan uca (yerel test sitesi)
- [ ] Güvenlik negatif testleri
- [ ] README (Türkçe, §20 başlıkları)
- [ ] Temiz klonla kurulum doğrulaması

## Kabul kriterleri (§23)
| # | Kriter | Durum | Kanıt |
|---|---|---|---|
| 1 | Yerelde açılır | [ ] | |
| 2 | Proje oluşturma | [ ] | |
| 3 | Tarama ayarları değiştirilebilir | [ ] | |
| 4 | İzin onayı | [ ] | |
| 5 | Gerçek siteyi tarama | [ ] | |
| 6 | robots/kapsam uyumu | [ ] | |
| 7 | HTML + render DOM analizi | [ ] | |
| 8 | İlerleme takibi | [ ] | |
| 9 | Gerçek veriden sorunlar | [ ] | |
| 10 | Kanıt + çözüm önerisi | [ ] | |
| 11 | URL detayları | [ ] | |
| 12 | CSV + HTML rapor | [ ] | |
| 13 | Eski taramalar korunur | [ ] | |
| 14 | İki tarama karşılaştırma | [ ] | |
| 15 | Güvenlik önlemleri | [ ] | |
| 16 | Testler çalıştırıldı | [ ] | |
| 17 | README eksiksiz | [ ] | |
