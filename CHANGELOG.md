# Değişiklik Günlüğü

Bu projedeki tüm önemli değişiklikler bu dosyada belgelenir.
Biçim [Keep a Changelog](https://keepachangelog.com/tr-TR/1.1.0/) esaslıdır; sürümleme [Semantic Versioning](https://semver.org/lang/tr/) kurallarına uyar.

## [Yayımlanmamış]

## [1.0.0] — 2026-10-10

İlk kararlı sürüm.

### Eklendi
- **Tarama motoru:** asenkron HTTPX fetcher (boyut sınırı, yeniden deneme, 429/503 uyarlamalı geri çekilme, `Retry-After`), BFS frontier, checkpoint ile durdur/devam ettir, eşzamanlı en fazla 3 tarama.
- **Render modları:** Standart, JavaScript (Playwright Chromium) ve Hibrit; ham HTML ile render DOM karşılaştırması.
- **Kapsam ve politika:** robots.txt (RFC 9309, joker, en uzun eşleşme), sitemap / sitemap index / gzip (XXE ve zip-bombası korumalı), alan adı / alt alan / include-exclude kuralları, `max_urls` ve derinlik sınırları.
- **SEO analizleri:** 100+ sorun kodu (HTTP, URL, title, description, başlıklar, canonical, robots direktifleri, görseller, bağlantılar, içerik, yapılandırılmış veri, Open Graph/Twitter, hreflang, render farkları); site geneli kontroller (yinelenen ve SimHash ile benzer içerik, kırık iç bağlantılar, redirect zincir/döngüleri, canonical hedefleri, hreflang karşılıklılık, yetim sayfa adayları, sitemap tutarlılığı).
- **Indexability:** taranabilir / teknik olarak indexlenebilir / gerçek indeks ayrımı.
- **Önceliklendirme:** yaygınlık, sayfa önemi, şablon geneli sorunlar ve indexlenemez bağlama göre önem ayarı.
- **Yönetim paneli (FastAPI + HTMX):** dashboard, proje ve tarama ayarları, izin onaylı tarama başlatma, canlı ilerleme, sunucu tarafı filtreli URL tablosu, URL detay sayfası, sorunlar ekranı.
- **Raporlama:** 10 tür CSV dışa aktarma (UTF-8 BOM, formül enjeksiyonu koruması), sıkı CSP'li bağımsız HTML raporu, sağlık puanı + güvenilirlik göstergesi (`docs/SCORING.md`), iki taramanın karşılaştırması.
- **Yedekleme:** zip + manifest yedek, doğrulamalı geri yükleme (arayüz ve `python run.py --backup/--restore`).
- **Arayüz:** Türkçe (varsayılan) ve İngilizce, açık / koyu / sistem teması, mobil uyumlu düzen, Z + geometrik örümcek logosu.
- **Kurulum:** `python run.py` ile tek komutta sanal ortam, bağımlılık ve Chromium kurulumu.

### Güvenlik
- SSRF koruması: loopback, özel, link-local ve metadata adresleri bağlantı anında engellenir; Playwright alt istekleri filtrelenir; localhost yalnızca `ZERQON_ALLOW_LOCALHOST` + proje ayarı ile açılır.
- Arayüz yalnızca `127.0.0.1` adresini dinler; TrustedHost, aynı köken (CSRF) denetimi, CSP ve güvenlik başlıkları.
- Parametrik SQL, beyaz listeli sıralama sütunları, XSS kaçışı, güvenli dosya adları, loglarda gizli bilgi maskeleme.
- Telemetri ve hesap sistemi yoktur.

[Yayımlanmamış]: https://github.com/tahafurkanbayar/zerqon-spider/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/tahafurkanbayar/zerqon-spider/releases/tag/v1.0.0
