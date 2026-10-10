<p align="center">
  <img src="zerqon/web/static/img/logo-mark.svg" width="96" height="96" alt="Zerqon Spider logosu">
</p>

<h1 align="center">Zerqon Spider</h1>
<p align="center"><b>Crawl Deeper. Discover More.</b><br>Advanced SEO Crawler &amp; Auditor</p>

Zerqon Spider, **sahibi olduğunuz veya tarama izniniz bulunan** web sitelerini tarayan, teknik SEO sorunlarını
teknik kanıtlarıyla tespit eden, bağlama göre önceliklendiren ve profesyonel raporlar üreten, **tamamen yerel**
çalışan bir teknik SEO denetim yazılımıdır. Screaming Frog SEO Spider'a işlevsel bir alternatif olarak tasarlanmıştır.

- Veriler yalnızca sizin bilgisayarınızda saklanır. **Telemetri, hesap sistemi veya üçüncü taraf analiz servisi yoktur.**
- Yönetim arayüzü varsayılan olarak yalnızca `127.0.0.1` adresini dinler.
- Güncel sürüm: **v1.0.0** — [sürümler](https://github.com/tahafurkanbayar/zerqon-spider/releases) · [değişiklik günlüğü](CHANGELOG.md)

---

## İçindekiler
1. [Özellikler](#özellikler)
2. [Teknoloji yığını](#teknoloji-yığını)
3. [Sistem gereksinimleri](#sistem-gereksinimleri)
4. [Kurulum ve ilk çalıştırma](#kurulum-ve-ilk-çalıştırma)
5. [Kullanım](#kullanım)
6. [Proje mimarisi](#proje-mimarisi)
7. [Veritabanı yapısı](#veritabanı-yapısı)
8. [Tarama ve izin politikası](#tarama-ve-izin-politikası)
9. [Veri saklama konumu](#veri-saklama-konumu)
10. [Yedekleme ve geri yükleme](#yedekleme-ve-geri-yükleme)
11. [Testler](#testler)
12. [Performans ve sınırlar](#performans-ve-sınırlar)
13. [Bilinen eksikler ve sınırlamalar](#bilinen-eksikler-ve-sınırlamalar)
14. [Sorun giderme](#sorun-giderme)

---

## Özellikler

**Tarama motoru**
- Dahili bağlantılarla genişlik-öncelikli (BFS) keşif; XML sitemap, sitemap index ve `.gz` desteği
- `robots.txt` (RFC 9309: `*` ve `$` jokerleri, en uzun eşleşme, `Crawl-delay`) — kurallara her zaman uyulur
- Üç mod: **Standart** (HTTP + HTML), **JavaScript** (Playwright/Chromium), **Hibrit** (yalnızca JS'e bağımlı görünen sayfalar render edilir)
- Ham HTML ile render edilmiş DOM karşılaştırması (title, H1, canonical, robots, kelime ve bağlantı farkları)
- Ayarlanabilir: URL sınırı (asla aşılmaz), derinlik, eşzamanlılık, istek aralığı, zaman aşımı, tekrar deneme, User-Agent, alt alan adları, regex dahil/hariç kuralları, sitemap ve görsel kontrolü
- 429/503'te `Retry-After` destekli uyarlamalı geri çekilme; yanıt boyutu ve render süresi sınırları
- Yönlendirmeler tek tek kaydedilir (her adım kapsam/robots/güvenlik kontrolünden geçer); zincir ve döngü tespiti
- **Durdurma ve kaldığı yerden devam ettirme**; uygulama kapanırsa yarım kalan tarama "yarım kaldı" olarak işaretlenir
- **SSRF koruması:** loopback, özel ağ, link-local, CGNAT ve bulut metadata adresleri engellenir; IP kontrolü bağlantı anında yapılır (DNS rebinding'e karşı)

**Teknik SEO analizleri (100+ kontrol)**
HTTP/yönlendirme · URL yapısı ve varyasyonları · Title · Meta description · Başlık hiyerarşisi · Canonical (hedef durumu, zincir, noindex çakışması, bağlama duyarlı eksiklik) · Indexlenebilirlik · Görseller (alt metni, boyut, kırık/büyük dosya, format, lazy loading) · İç bağlantılar (kırık, yönlendirmeye giden, nofollow, boş anchor, derinlik, yetim sayfa **adayları**) · İçerik (düşük içerik, birebir yinelenen, SimHash ile benzer içerik **adayları**) · JavaScript render farkları · Yapılandırılmış veri (JSON-LD/Microdata/RDFa, sözdizimi, temel alanlar) · Open Graph / Twitter Card · hreflang (kod biçimi, karşılıklılık, hedef durumu) · Sitemap ve robots.txt tutarlılığı · Viewport

**Önceliklendirme ve puan**
- 5 önem seviyesi (Kritik, Yüksek, Orta, Düşük, Bilgi); yaygınlık, sayfa önemi ve indexlenebilirlik bağlamına göre ayarlanır
- 0–100 **Teknik SEO sağlık puanı** + güvenilirlik göstergesi (algoritma: [`docs/SCORING.md`](docs/SCORING.md)). *Google'ın resmi puanı değildir.*

**Arayüz** (Türkçe varsayılan, İngilizce; açık/koyu tema; responsive)
- Dashboard, proje yönetimi, izin onaylı tarama başlatma, canlı ilerleme (HTMX)
- Sunucu tarafı arama/filtre/sıralama/sayfalama ile URL tablosu, seçili satırları dışa aktarma
- URL detay sayfası, kanıt ve çözüm önerili sorunlar ekranı, iki taramanın karşılaştırılması

**Raporlama**
- 10 türde CSV (UTF-8 BOM, Türkçe karakter uyumlu, formül enjeksiyonuna karşı korumalı)
- Tek dosyalık, internetsiz açılan, güvenli escape'li **HTML denetim raporu** (TR/EN)
- Yedekleme ve geri yükleme (arayüz ve komut satırı)

---

## Teknoloji yığını

| Bileşen | Sürüm (requirements.txt) |
|---|---|
| Python | 3.12 (3.13 de desteklenir) |
| FastAPI / Starlette | 0.143.0 / 1.7.0 |
| Uvicorn | 0.54.0 |
| HTTPX / httpcore | 0.28.1 / 1.0.9 |
| lxml (HTML ve XML ayrıştırma) | 6.1.3 |
| Pydantic / pydantic-settings | 2.14.0 / 2.15.0 |
| Jinja2 | 3.1.6 |
| Playwright (Chromium) | 1.63.0 |
| SQLite | Python ile gelen (geliştirmede 3.53.1), WAL modu |
| HTMX | 2.0.4 (repo içinde, CDN kullanılmaz) |
| Test | pytest 9.1.1, pytest-asyncio 1.4.0 |

Ön yüz: HTML5, CSS3, Vanilla JavaScript ve HTMX. Harici font, CDN veya analiz betiği yoktur.

---

## Sistem gereksinimleri

- **Python 3.12** (veya 3.13) — Windows, Linux ve macOS
- İlk kurulumda **internet bağlantısı** (Python paketleri ve ~150 MB Chromium indirilir)
- ~600 MB disk (sanal ortam + Chromium) + tarama verileri için ek alan
- **Linux:** Chromium'un sistem kütüphaneleri gerekebilir (bkz. [Sorun giderme](#sorun-giderme)). Chromium kurulamasa bile standart tarama çalışır; yalnızca JavaScript/Hibrit mod devre dışı kalır.

---

## Kurulum ve ilk çalıştırma

### Tek komut

```bash
git clone https://github.com/tahafurkanbayar/zerqon-spider.git
cd zerqon-spider
python run.py
```

`run.py` yalnızca standart kütüphaneyi kullanır ve gerektiğinde:
1. Uygun Python 3.12/3.13 yorumlayıcısını bulur (mevcut yorumlayıcı → `py -3.12` → `python3.12` → `uv python find 3.12`),
2. `.venv` sanal ortamını oluşturur ve `requirements.txt` bağımlılıklarını kurar,
3. Playwright için Chromium'u indirir,
4. Veritabanını oluşturur / migration'ları uygular ve sunucuyu başlatıp tarayıcıyı açar: **http://127.0.0.1:8765/**

Sonraki çalıştırmalarda değişmeyen adımlar atlanır (`.venv/.zerqon-deps` ve `.venv/.zerqon-chromium` damgaları).

Seçenekler: `python run.py --no-browser --port 9000`, `--dev` (test bağımlılıkları), `--skip-browser-install`,
`--migrate-only`, `--backup [dosya.zip]`, `--restore dosya.zip`.

> Sisteminizdeki varsayılan `python` 3.12 değilse Windows'ta `py -3.12 run.py`, Linux/macOS'ta `python3.12 run.py`
> da kullanabilirsiniz. Hiç Python 3.12 yoksa: https://www.python.org/downloads/ veya `uv python install 3.12`.

### Manuel kurulum

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m zerqon
```

**Linux / macOS**
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium        # Linux: gerekirse --with-deps
.venv/bin/python -m zerqon
```

### Yapılandırma (`.env`)

`.env.example` dosyasını `.env` olarak kopyalayın. Önemli değişkenler:

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `ZERQON_HOST` / `ZERQON_PORT` | `127.0.0.1` / `8765` | Yönetim arayüzü adresi |
| `ZERQON_DATA_DIR` | `./data` | Veritabanı, log, rapor, yedek dizini |
| `ZERQON_DEFAULT_LANGUAGE` | `tr` | `tr` veya `en` |
| `ZERQON_ALLOW_LOCALHOST` | `false` | Yerel geliştirme sitelerini taramaya izin verir (bkz. izin politikası) |
| `ZERQON_MAX_CONCURRENCY` | `20` | Tüm taramalar için eşzamanlılık üst sınırı |
| `ZERQON_MAX_URLS_HARD_LIMIT` | `500000` | Proje ayarından bağımsız mutlak URL üst sınırı |
| `ZERQON_MAX_BODY_BYTES` | `5242880` | Sayfa başına okunacak en fazla bayt |
| `ZERQON_RENDER_TIMEOUT_SECONDS` | `20` | Sayfa başına render zaman aşımı |
| `ZERQON_MAX_RENDER_CONTEXTS` | `3` | Eşzamanlı Chromium sayfa sayısı |

---

## Kullanım

1. **Yeni proje** oluşturun: ad, başlangıç URL'si ve tarama ayarları (limitler, kapsam, render modu, analiz eşikleri).
2. **Tarama başlat** ekranında site sahibi olduğunuzu / tarama izniniz olduğunu onaylayın.
3. **Canlı ilerlemeyi** izleyin (taranan, kuyruk, hata, hız, geçen süre, son URL, anlık sorunlar). İstediğiniz zaman **durdurun**; daha sonra **kaldığı yerden devam** ettirin.
4. Sonuçları **Genel bakış**, **URL'ler**, **Sorunlar** ve **Raporlar** sekmelerinde inceleyin.
5. Proje sayfasından iki taramayı seçip **karşılaştırın**.

---

## Proje mimarisi

```
run.py                      Tek komutlu başlatıcı (venv, bağımlılık, Chromium, sunucu)
zerqon/
├── __main__.py             python -m zerqon (migration + uvicorn, --backup/--restore)
├── config.py               Ayarlar (.env, pydantic-settings)
├── logging_config.py       Dönen log dosyası, gizli bilgi maskeleme
├── formatting.py           Sayı/tarih/boyut biçimlendirme
├── schemas.py              Pydantic doğrulama modelleri
├── i18n/                   Çeviri altyapısı + locales/{tr,en}*.json
├── db/                     SQLite bağlantısı, sürümlü migration'lar, repository'ler
├── crawler/                urls, scope, security (SSRF), robots, sitemap, fetcher, frontier,
│                           renderer (Playwright), store (toplu yazım), engine, manager, postprocess
├── parsing/                lxml HTML ayrıştırıcı, yapılandırılmış veri, metin/SimHash
├── analysis/               issues (registry), checks/ (sayfa + site kontrolleri), indexability,
│                           prioritization, scoring, snapshot, finalize
├── reports/                csv_export, html_report (+templates), compare, backup
└── web/                    FastAPI app, routes/, templates/ (Jinja2 + HTMX), static/
tests/                      pytest; fixtures/site.py = yerel test web sitesi
docs/                       SCORING.md, ai/ (proje hafızası: PROMPT, CONTEXT, ROADMAP, DECISIONS, PROGRESS)
```

**Akış:** `CrawlManager` her taramayı ayrı bir thread'de kendi asyncio döngüsüyle çalıştırır (arayüz engellenmez).
`CrawlEngine`: robots.txt → sitemap keşfi → BFS tarama (sayfa kontrolleri canlı çalışır) → ertelenmiş sitemap
URL'leri → görsel kontrolleri → sonlandırma (bağlantı grafiği, tık derinliği, yönlendirme zincirleri,
indexlenebilirlik, site kontrolleri, önceliklendirme, puan, özet).

**Yeni bir SEO kontrolü eklemek:** `zerqon/analysis/issues.py` içine kodu tanımlayın, `analysis/checks/` altında
`@page_check` veya `@site_check` ile işaretli bir fonksiyon yazın ve `tr`/`en` dosyalarına
`issues.<kod>.{name,desc,fix}` metinlerini ekleyin. Başka bir yerin değişmesi gerekmez
(`tests/test_analysis.py::test_every_issue_has_translations` eksik metni yakalar).

Mimari kararların gerekçeleri: [`docs/ai/DECISIONS.md`](docs/ai/DECISIONS.md).

---

## Veritabanı yapısı

SQLite, WAL modu, yabancı anahtarlar açık, tüm sorgular parametrik. Şema sürümlü migration'larla yönetilir
(`zerqon/db/migrations/NNNN_*.sql`, uygulananlar `schema_migrations` tablosunda).

| Tablo | İçerik |
|---|---|
| `projects` | Proje adı, başlangıç URL'si, varsayılan ayar kaydı, tarihler |
| `crawl_settings` | Ayarlar; her tarama başlarken kopyası alınır (eski taramalar korunur) |
| `crawl_jobs` | Tarama durumu, ilerleme, izin onayı zamanı, robots durumu, hata |
| `frontier` | Keşfedilen URL kuyruğu = **checkpoint** (devam ettirme) |
| `pages` | URL başına HTTP sonucu, indexlenebilirlik, bağlantı sayıları, derinlik, içerik hash'leri |
| `page_metadata` | Title, description, robots, canonical, H1, OG/Twitter, ham/render karşılaştırması |
| `headings`, `links`, `images`, `hreflang`, `structured_data` | Sayfa alt kayıtları |
| `image_resources` | Benzersiz görsellerin durum kodu ve boyutu |
| `redirects` | Yönlendirme zincirlerinin adımları |
| `sitemaps`, `sitemap_urls` | Sitemap dosyaları ve içerdikleri URL'ler |
| `issues` | Sorun kodu, kategori, temel/nihai önem, öncelik puanı, kanıt, sinyaller, tespit zamanı |
| `crawl_snapshots` | Tarama sonu özet (dashboard ve karşılaştırma için hızlı erişim, puan) |
| `crawl_events` | Kullanıcıya gösterilen olaylar (robots erişilemedi, render kullanılamıyor…) |
| `reports` | Oluşturulan HTML raporları |
| `app_settings` | Dil vb. uygulama tercihleri |

---

## Tarama ve izin politikası

- Her taramadan önce **site sahibi olduğunuzu veya tarama izniniz olduğunu açıkça onaylamanız** gerekir.
  Bu onay **sizin beyanınızdır**; Zerqon Spider site sahipliğini otomatik olarak doğrulamaz.
- `robots.txt` kurallarına her zaman uyulur. `robots.txt` 5xx/429 döndürür veya erişilemezse temkinli davranılır ve o host taranmaz; 4xx ise kısıtlama yok kabul edilir.
- Belirlenen URL sınırı ve kapsam kuralları **hiçbir koşulda aşılmaz**. Kapsam dışındaki alan adları taranmaz; dış bağlantılar yalnızca kaydedilir.
- Varsayılan olarak istekler arası 250 ms ve 4 eşzamanlı istek kullanılır; sunucu 429/503 döndürdüğünde hız otomatik düşer.
- **SSRF koruması:** loopback (127.0.0.0/8, ::1), özel ağlar (10/8, 172.16/12, 192.168/16, fc00::/7), link-local, CGNAT, multicast ve bulut metadata adresleri (169.254.169.254 vb.) her URL ve yönlendirme hedefi için engellenir. Kontrol, bağlantı kurulurken çözümlenen IP üzerinde yapılır. Playwright'ın alt istekleri de aynı politikadan geçer.
- **Localhost modu:** yerel geliştirme sitelerini taramak için `.env`'de `ZERQON_ALLOW_LOCALHOST=true` **ve** proje ayarında "Localhost'a izin ver" seçili olmalıdır. Bu mod yalnızca loopback'i açar; özel ağlar ve metadata adresleri yine engellidir.
- Uygulama hedef sitelerde **hiçbir değişiklik yapmaz**; yalnızca GET/HEAD istekleri gönderir.

---

## Veri saklama konumu

Varsayılan: proje kökünde `data/` (`ZERQON_DATA_DIR` ile değiştirilebilir). Ayarlar sayfasında gerçek yollar gösterilir.

```
data/
├── zerqon.db        Tüm projeler, taramalar ve sonuçlar (SQLite, WAL)
├── logs/zerqon.log  Dönen log dosyası (5 × 5 MB); URL'deki şifre/token ve çerez değerleri maskelenir
├── reports/         Oluşturulan HTML raporları
└── backups/         Yedekler ve geri yükleme öncesi güvenlik kopyaları
```

`data/` ve `.env` Git'e eklenmez.

---

## Yedekleme ve geri yükleme

- **Arayüz:** Ayarlar → *Yedekleme ve geri yükleme* → "Şimdi yedekle" / "Yedekten geri yükle".
- **Komut satırı:**
  ```bash
  python run.py --backup                 # data/backups/zerqon-backup-<zaman>.zip
  python run.py --backup yedegim.zip
  python run.py --restore yedegim.zip
  ```
Yedek, SQLite online backup API ile alınan tutarlı bir anlık görüntü ve `manifest.json` içerir. Geri yüklemede arşiv
içeriği, `PRAGMA integrity_check` ve şema sürümü doğrulanır; mevcut veritabanının güvenlik kopyası
`backups/pre-restore-*.zip` olarak alınır. Devam eden tarama varken geri yükleme yapılamaz.

---

## Testler

```bash
python run.py --dev --migrate-only     # test bağımlılıklarını kur (veya: pip install -r requirements-dev.txt)
.venv/Scripts/python -m pytest -q      # Windows
.venv/bin/python -m pytest -q          # Linux/macOS
```

Testler üçüncü taraf canlı sitelere **bağımlı değildir**; `tests/fixtures/site.py` kasıtlı SEO sorunları içeren yerel bir
web sitesini gerçek HTTP ile sunar. Kapsam: URL normalizasyonu, kapsam kuralları, robots.txt, sitemap (XXE dahil),
SSRF negatif testleri, canonical/title/description/heading analizleri, indexlenebilirlik, yönlendirme zincirleri,
önceliklendirme, sağlık puanı, CSV (formül enjeksiyonu), HTML raporu (XSS/escape, harici kaynak yok),
karşılaştırma, yedekleme, veritabanı işlemleri, durdur/devam, 429 geri çekilme, Playwright JS/hibrit render ve
arayüz üzerinden uçtan uca başarılı senaryo. Chromium kurulu değilse render testleri otomatik atlanır.

Son çalıştırma: **148 test, 148 geçti** (Windows 10, Python 3.12.15).

---

## Performans ve sınırlar

- Mimari 1.000, 10.000 ve daha büyük URL kümelerine göre tasarlanmıştır: asenkron istekler, kontrollü eşzamanlılık,
  bellekte yalnızca kuyruk ve URL anahtarları, SQLite'a toplu ve atomik yazım, sunucu tarafı sayfalama,
  O(n²) yerine LSH bantlı benzer içerik karşılaştırması.
- **Hız garantisi verilmez**: gerçek hız hedef sunucuya, ağa, istek aralığına ve render moduna bağlıdır.
  Yerel test sitesinde (28 URL, 4 eşzamanlı, gecikmesiz) standart tarama birkaç saniye sürer;
  bu ölçüm gerçek siteler için gösterge değildir.
- JavaScript modu sayfa başına bir tarayıcı render'ı gerektirdiği için standart moddan belirgin şekilde yavaştır;
  `max_render_pages` ve `ZERQON_MAX_RENDER_CONTEXTS` ile sınırlandırılır.
- Aynı anda en fazla 3 tarama çalışabilir. Sayfa başına en fazla 5.000 bağlantı ve 2.000 görsel kaydedilir;
  sitemap dosyası sınırı 100, sitemap başına 50.000 URL.

---

## Bilinen eksikler ve sınırlamalar

- **Gerçek Google indeks durumu bilinmez:** Search Console entegrasyonu yoktur; yalnızca *teknik* indexlenebilirlik hesaplanır.
- **Core Web Vitals ölçülmez;** yanıt süreleri tek bir tarama isteğine aittir, saha verisi değildir.
- **Dış bağlantıların durum kodu kontrol edilmez** (kapsam dışına istek gönderilmez).
- **Yapılandırılmış veri** yalnızca sözdizimi ve yaygın türlerin temel alanları açısından kontrol edilir; Google zengin sonuç kurallarının tamamı doğrulanmaz.
- **hreflang** kodları biçim (BCP 47) ve yaygın hatalar açısından doğrulanır; tam ISO 639/3166 listesiyle karşılaştırılmaz (biçime uyan ama var olmayan kodlar yakalanmaz).
- **Yetim sayfalar** yalnızca sitemap'e göre *aday* olarak raporlanır; harici URL listesi (ör. analytics/log) içe aktarma yoktur.
- **Benzer içerik** SimHash tahminidir; şablon metni yoğun sayfalar da eşleşebilir.
- Sayfa düzeyi `robots.txt` engelli URL'ler için içerik analizi yapılmaz (istek gönderilmez).
- Playwright alt istekleri SSRF kontrolünden geçer, ancak Chromium kendi DNS çözümlemesini yaptığı için render sırasında teorik DNS-rebinding riski tamamen ortadan kaldırılamaz; WebSocket istekleri filtrelenmez.
- Yanıt süresi "TTFB + gövde indirme" toplamıdır; ayrı TTFB ölçümü yoktur.
- Kimlik doğrulama gerektiren (login) sayfalar ve özel HTTP başlıkları/çerezlerle tarama desteklenmez.
- Proje lisansı henüz belirlenmemiştir.

---

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| `Python 3.12 (veya 3.13) bulunamadı` | Python 3.12 kurun veya `uv python install 3.12`; sonra `py -3.12 run.py` / `python3.12 run.py` |
| Bağımlılık kurulumu başarısız | İnternet bağlantısını ve proxy ayarlarını kontrol edin; `.venv` klasörünü silip tekrar `python run.py` |
| "JavaScript render başlatılamadı" olayı | `.venv/…/python -m playwright install chromium`; Linux'ta `--with-deps` ile sistem kütüphanelerini kurun. Standart mod çalışmaya devam eder |
| Yerel site (`localhost`) "Güvenlik engeli" | `.env`'de `ZERQON_ALLOW_LOCALHOST=true` + proje ayarında "Localhost'a izin ver" |
| Tüm URL'ler robots.txt engeli / tarama hemen bitiyor | Tarama olaylarında robots durumunu kontrol edin; robots.txt 5xx döndürüyorsa temkinli olarak tarama yapılmaz |
| Çok sayıda zaman aşımı / 429 | Eşzamanlılığı düşürün, istek aralığını ve zaman aşımını artırın |
| SSL/TLS hatası | Sitenin sertifikasını kontrol edin (süresi dolmuş, alan adı uyumsuz, eksik ara sertifika) |
| "Veritabanı meşgul" / "Disk dolu" | Birkaç saniye sonra tekrar deneyin / veri dizininde yer açın; yarım kalan taramayı devam ettirin |
| Port kullanımda | `python run.py --port 9000` veya `.env`'de `ZERQON_PORT` |
| Ayrıntılı hata | `data/logs/zerqon.log` dosyasına bakın (gizli bilgiler maskelenir) |

---

<p align="center"><sub>Zerqon Spider v1.0.0 — Crawl Deeper. Discover More.</sub></p>
