# Orijinal Proje Promptu (Değiştirilmeden Saklanır)

> Bu dosya, projenin kaynak gereksinim belgesidir. Kullanıcı tarafından 2026-10-09 tarihinde verilmiştir.
> **Düzenleme yapılmaz.** Yorumlar/yorumlamalar `DECISIONS.md` dosyasına, kapsam takibi `ROADMAP.md` dosyasına yazılır.
> Ek talimatlar (konuşma sırasında gelen) en altta "Ek Talimatlar" bölümündedir.

---

# PROJE: Profesyonel SEO Spider ve Teknik SEO Denetim Platformu

## 1. Genel Amaç

Boş bir Git deposunda, Screaming Frog SEO Spider'a işlevsel bir alternatif oluşturabilecek, profesyonel, hızlı, güvenli ve genişletilebilir bir **SEO Tarama ve Teknik SEO Analiz Yazılımı** geliştir.

Uygulama, kullanıcıların sahip oldukları veya tarama iznine sahip oldukları web sitelerini analiz etmelerini, teknik SEO problemlerini tespit etmelerini, bu problemleri önceliklendirmelerini ve kapsamlı raporlar oluşturmalarını sağlamalıdır.

Uygulama yalnızca basit bir URL tarayıcısı olmamalıdır. Gerçek bir teknik SEO uzmanının kullanabileceği, detaylı analiz gerçekleştiren, anlaşılır sonuçlar sunan ve gelecekte yeni özelliklerle genişletilebilen profesyonel bir yazılım olmalıdır.

**Temel hedef:** Kullanıcının bir web sitesi adresini girmesi, tarama başlatması, sonuçları gerçek zamanlı izlemesi, SEO problemlerini incelemesi ve kapsamlı denetim raporları oluşturması.

İlk sürüm, çalışan ve test edilmiş bir ürün olmalıdır. Yalnızca örnek ekranlardan veya sahte verilerden oluşmamalıdır.

---

## 2. Zorunlu Teknoloji Yığını

Aşağıdaki teknolojileri kullan:

- Python 3.12
- FastAPI
- SQLite
- Playwright
- HTMX
- HTML5
- CSS3
- Vanilla JavaScript
- Python HTTP istemcisi (örneğin HTTPX)
- HTML ayrıştırma için BeautifulSoup veya lxml
- Pydantic ile veri doğrulama

Gerektiğinde yardımcı Python kütüphaneleri kullanılabilir.

Ancak ana teknoloji yığını değiştirilmemelidir.

React, Next.js, Vue, Laravel, PostgreSQL, MongoDB veya farklı bir ana teknoloji yığını önerme.

Kod mimarisi modüler, bakımı kolay ve genişletilebilir olmalıdır.

Veri işleme, tarama, analiz, raporlama ve kullanıcı arayüzü birbirinden ayrılmalıdır.

---

## 3. Uygulama Arayüzü

Modern, profesyonel ve kullanıcı dostu bir yönetim paneli geliştir.

Arayüz klasik bir masaüstü yazılımının karmaşıklığını azaltmalı, ancak profesyonel SEO araçlarında bulunan veri yoğunluğunu korumalıdır.

### Genel tasarım

- Modern SaaS tarzı arayüz
- Sol tarafta gezinme menüsü
- Üst alanda aktif proje ve tarama bilgileri
- Dashboard kartları
- Gelişmiş veri tabloları
- Filtreleme ve arama
- Açık ve koyu tema
- Responsive tasarım
- Anlaşılır grafikler
- SEO sorunları için renk ve simge destekli göstergeler
- Boş veri, yüklenme, başarılı işlem ve hata durumları

### Dil desteği

Uygulamanın varsayılan dili Türkçe olmalıdır.

Türkçe ve İngilizce dil altyapısı oluştur.

Bütün arayüz metinleri merkezi çeviri dosyalarından yönetilmelidir. Metinler şablonların içine sabit olarak dağınık biçimde yazılmamalıdır.

### Ana sayfa

Dashboard üzerinde aşağıdaki bilgiler bulunmalıdır:

- Toplam proje sayısı
- Taranan toplam URL
- Başarılı ve başarısız URL sayıları
- Kritik, yüksek, orta ve düşük öncelikli SEO sorunları
- Son taramalar
- Devam eden taramalar
- HTTP durum kodu dağılımı
- Indexlenebilir ve indexlenemez sayfalar
- Ortalama yanıt süresi
- Önceki taramaya göre değişimler

Kullanıcı tek bakışta web sitesinin teknik durumunu anlayabilmelidir.

---

## 4. Proje Yönetimi

Kullanıcı birden fazla web sitesi projesi oluşturabilmelidir.

Her proje için:

- Proje adı
- Web sitesi adresi
- Oluşturulma tarihi
- Son tarama tarihi
- Tarama geçmişi
- Tarama ayarları
- Kayıtlı raporlar
- Toplam SEO sorunları
- Önceki taramalarla karşılaştırmalar

saklanmalıdır.

Projeler birbirinden bağımsız olmalıdır.

Bir projenin eski tarama sonuçları yeni tarama başlatıldığında silinmemelidir.

Kullanıcı geçmiş taramaları görüntüleyebilmelidir.

---

## 5. SEO Tarama Motoru

Güçlü ve güvenilir bir web tarama motoru oluştur.

### Tarama özellikleri

- Dahili bağlantıları takip ederek sayfaları keşfetme
- XML Sitemap üzerinden URL keşfi
- Sitemap index desteği
- robots.txt dosyasını okuma
- robots.txt kurallarına uyma
- HTTP durum kodlarını kaydetme
- HTTP yönlendirmelerini izleme
- Redirect zincirlerini tespit etme
- Canonical etiketlerini analiz etme
- Nofollow bağlantılarını tespit etme
- Meta robots ve X-Robots-Tag analizleri
- İç bağlantı analizi
- Dış bağlantı analizi
- Görsel bağlantı analizi
- JavaScript ile oluşturulan sayfaları render etme
- Ham HTML ile render edilmiş DOM arasındaki farkları analiz etme

### Tarama modları

**1. Standart tarama**

Hızlı HTTP istekleri üzerinden HTML analizi gerçekleştir.

**2. JavaScript taraması**

Playwright kullanarak sayfaları gerçek tarayıcı ortamında render et.

**3. Hibrit tarama**

Önce standart tarama gerçekleştir. Gerekli sayfalar için JavaScript render analizini ayrıca çalıştır.

### Tarama kontrolleri

Kullanıcı aşağıdaki ayarları değiştirebilmelidir:

- Maksimum URL sayısı
- Maksimum tarama derinliği
- Eşzamanlı istek sayısı
- İstekler arası bekleme süresi
- İstek zaman aşımı
- Maksimum tekrar deneme sayısı
- User-Agent
- Alt alan adlarını kapsama seçeneği
- URL dahil etme ve hariç tutma kuralları
- JavaScript render seçeneği
- Sitemap tarama seçeneği

Tarama motoru kontrollü eşzamanlılık ile çalışmalıdır.

Aşırı istek göndererek hedef sunucuya zarar vermemelidir.

HTTP 429 ve 503 durumlarında uygun geri çekilme politikası uygulanmalıdır.

robots.txt içindeki geçerli kısıtlamalara uyulmalıdır. Belirlenmiş URL sınırı ve kapsam kuralları hiçbir şekilde aşılmamalıdır.

### Güvenlik

Tarama başlamadan önce kullanıcı, site sahibi olduğunu veya tarama iznine sahip olduğunu açıkça onaylamalıdır.

Bu onayın kullanıcı beyanı olduğu, otomatik mülkiyet doğrulaması olmadığı kabul edilmelidir.

SSRF saldırılarına karşı koruma sağla.

Her URL ve yönlendirme hedefi doğrulanmalıdır. Varsayılan olarak loopback, özel ağ, link-local ve bulut metadata adreslerine erişim engellenmelidir.

Yerel geliştirme sitelerinin taranması gerektiğinde yalnızca açıkça etkinleştirilen, kontrollü bir localhost modu kullanılmalıdır.

Tarama kapsamı dışındaki alan adları otomatik olarak taranmamalıdır.

Playwright oturumları, işlem süreleri ve kaynak tüketimi sınırlandırılmalıdır.

---

## 6. Teknik SEO Analiz Modülleri

Aşağıdaki analizleri geliştir.

### A. HTTP ve URL analizi

- 200, 301, 302, 307, 308, 400, 403, 404, 410 ve 500 serisi durum kodları
- Kırık bağlantılar
- Yönlendirme zincirleri
- Redirect döngüleri
- HTTP/HTTPS tutarsızlıkları
- Gereksiz yönlendirmeler
- URL uzunluğu
- URL parametreleri
- URL normalizasyonu
- Yinelenen URL varyasyonları
- Dahili bağlantı hataları

### B. Başlık analizi (Title)

- Eksik title
- Boş title
- Yinelenen title
- Çok kısa title
- Çok uzun title
- Bir sayfadaki birden fazla title
- Title ile H1 tutarsızlıkları

Karakter sayısı eşikleri yapılandırılabilir olmalıdır. Öneriler kesin arama motoru kuralları olarak sunulmamalıdır.

### C. Meta Description analizi

- Eksik açıklama
- Boş açıklama
- Yinelenen açıklama
- Çok kısa açıklama
- Çok uzun açıklama

### D. Heading analizi

- Eksik H1
- Birden fazla H1
- Yinelenen H1
- Boş heading
- H1 ile title karşılaştırması
- H1-H6 hiyerarşisi
- Mantıksız heading geçişleri

### E. Canonical analizi

- Eksik canonical
- Birden fazla canonical
- Geçersiz canonical
- Canonical hedefinin yönlendirilmesi
- Canonical hedefinin 404 olması
- Canonical ile noindex çakışmaları
- Sitemap ve canonical tutarsızlıkları
- HTTP/HTTPS canonical farklılıkları

Canonical bulunmaması her sayfa için otomatik hata sayılmamalıdır. Sorun tespiti gerçek bağlama göre yapılmalıdır.

### F. Indexability analizi

Her URL için teknik indexlenebilirlik durumunu hesapla.

Aşağıdaki sinyalleri değerlendir:

- HTTP durum kodu
- Meta robots
- X-Robots-Tag
- robots.txt engelleri
- Canonical ilişkileri
- Yönlendirmeler
- Noindex
- Nofollow

Crawl edilebilirlik, teknik indexlenebilirlik ve Google tarafından gerçekten indekslenmiş olma durumları birbirinden ayrılmalıdır.

Google Search Console bağlantısı olmadan gerçek Google indeks durumunu bildiğini iddia etme.

### G. Görsel SEO analizi

- Eksik alt metni
- Boş alt metni
- Kırık görsel bağlantıları
- Büyük görsel dosyaları
- Görsel formatları
- Görsel boyut bilgileri
- Yinelenen görsel kaynakları
- Lazy loading kullanımı

Dekoratif görseller için boş alt metninin geçerli olabileceğini dikkate al.

### H. İç bağlantı analizi

- Sayfa başına iç bağlantı sayısı
- Gelen bağlantı sayısı
- Giden bağlantı sayısı
- Nofollow bağlantılar
- Kırık dahili bağlantılar
- Yüksek bağlantı derinliği
- Bağlantı metinleri (anchor text)
- Sitemap'te bulunup taranan sayfalardan bağlantı almayan URL adayları

Yetim sayfaları kesin olarak bildiğini iddia etme. Harici URL envanteri veya sitemap üzerinden tespit edilenleri **yetim sayfa adayı** olarak işaretle.

### I. İçerik analizi

- Sayfa kelime sayısı
- Görünür metin miktarı
- Çok düşük içerik miktarı
- Tamamen aynı içerikler
- Benzer içerik adayları
- Başlık ve açıklama tekrarları
- Render edilmiş içerik ile ham HTML karşılaştırması

Benzer içerik tespitinde gerekirse normalize edilmiş metin hash'leri veya uygun benzerlik algoritmaları kullan.

### J. Yapılandırılmış veri analizi

- JSON-LD tespiti
- Microdata tespiti
- RDFa tespiti
- JSON-LD sözdizimi kontrolü
- Schema.org türlerinin listelenmesi
- Temel zorunlu alan kontrolleri
- Sayfalarda yapılandırılmış veri bulunma durumu

Google'ın bütün zengin sonuç kurallarını eksiksiz doğruladığını iddia etme.

### K. Sosyal medya meta etiketleri

- Open Graph title
- Open Graph description
- Open Graph image
- Open Graph URL
- Twitter/X Card etiketleri
- Eksik sosyal paylaşım verileri

### L. Çok dilli SEO

- Hreflang etiketlerini incele
- Geçersiz dil/bölge kodlarını tespit et
- Hreflang hedeflerini kontrol et
- Karşılıklı hreflang ilişkilerini analiz et
- Hreflang ile canonical tutarsızlıklarını raporla

### M. Sitemap ve robots.txt

- Sitemap erişilebilirliği
- Sitemap XML geçerliliği
- Sitemap URL durumları
- Sitemap ve canonical tutarlılığı
- Sitemap içerisinde noindex URL bulunması
- robots.txt erişilebilirliği
- Sitemap bildirimleri
- Tarama engelleri

---

## 7. SEO Sorunları ve Önceliklendirme Motoru

Tespit edilen her sorun standart bir veri modeliyle saklanmalıdır.

Her sorun aşağıdaki alanlara sahip olmalıdır:

- Sorun kodu
- Sorun adı
- Açıklama
- Etkilenen URL
- Sorun kategorisi
- Önem seviyesi
- Teknik kanıt
- Tespit tarihi
- Önerilen çözüm
- İlgili teknik sinyaller

### Önem seviyeleri

1. Kritik
2. Yüksek
3. Orta
4. Düşük
5. Bilgilendirme

Önceliklendirme yalnızca sabit kurallara dayanmamalıdır. Uygun durumlarda sorunun yaygınlığı, etkilenen sayfa sayısı ve teknik etkisi dikkate alınmalıdır.

Örneğin:

- Çok sayıda önemli URL'nin 5xx hatası vermesi kritik olabilir.
- Tek bir sayfada eksik meta description genellikle düşük veya orta önceliklidir.
- Indexlenmesi amaçlanan sayfalarda yanlışlıkla noindex bulunması yüksek öncelikli olabilir.

Sorunlar kategori ve önem düzeyine göre filtrelenebilmelidir.

Her sorun için kullanıcıya doğrudan uygulanabilir çözüm önerisi gösterilmelidir.

---

## 8. Tarama Sonuçları Ekranı

Taranan URL'ler gelişmiş bir tabloda listelenmelidir.

Örnek sütunlar:

- URL
- HTTP Status
- Content Type
- Indexability
- Title
- Meta Description
- H1
- Canonical
- Word Count
- Inlinks
- Outlinks
- Crawl Depth
- Response Time
- Issues Count

Tablo özellikleri:

- Anlık arama
- Çoklu filtreleme
- Sütuna göre sıralama
- Sayfalama
- Seçilen satırların dışa aktarılması
- URL detaylarını açma
- Durum koduna göre filtreleme
- SEO sorununa göre filtreleme

HTMX ile gereksiz tam sayfa yenilemelerinden kaçınılmalıdır.

Büyük sonuç kümelerinde filtreleme, sıralama ve sayfalama sunucu tarafında yapılmalıdır.

### URL detay sayfası

Her URL için ayrı detay ekranı olmalıdır.

Bu ekranda:

- Temel HTTP bilgileri
- Meta etiketler
- Heading yapısı
- Canonical bilgisi
- İç ve dış bağlantılar
- Görseller
- Yapılandırılmış veriler
- Indexability analizi
- Tespit edilen sorunlar
- Ham/render içerik karşılaştırması

görüntülenebilmelidir.

---

## 9. Gerçek Zamanlı Tarama Takibi

Tarama sürerken kullanıcı ilerlemeyi izleyebilmelidir.

Gösterilecek veriler:

- Taranan URL sayısı
- Kuyrukta bekleyen URL sayısı
- Hatalı URL sayısı
- Tarama hızı
- Geçen süre
- Son taranan URL
- Anlık bulunan SEO sorunları
- Aktif tarama durumu

Tarama işlemi kullanıcı arayüzünü engellememelidir.

Kullanıcı taramayı güvenli biçimde durdurabilmelidir.

İptal edildiğinde tamamlanan tarama kayıtları korunmalıdır.

Uygulama beklenmedik şekilde kapandığında yarım kalan taramalar veritabanında açıkça işaretlenmelidir.

Uygun bir checkpoint mekanizmasıyla taramanın devam ettirilmesi desteklenmelidir.

---

## 10. SEO Sağlık Puanı

Her proje ve tarama için 0-100 arasında bir teknik SEO sağlık puanı hesapla.

Puanın hesaplanmasında:

- Kritik sorunlar
- Yüksek öncelikli sorunlar
- Indexability problemleri
- Kırık bağlantılar
- Meta veri sorunları
- Canonical tutarsızlıkları
- Tarama kapsamı

gibi unsurlar kullanılabilir.

Ancak bu puanın Google'ın resmi değerlendirme puanı olmadığı açıkça belirtilmelidir.

Puanlama algoritması belgelenmeli ve deterministik olmalıdır.

Eksik tarama veya düşük kapsama sahip projelerde puanın güvenilirliği ayrıca gösterilmelidir.

---

## 11. Geçmiş Taramaları Karşılaştırma

Aynı projeye ait iki tarama karşılaştırılabilmelidir.

Kullanıcı şu değişimleri görebilmelidir:

- Yeni bulunan SEO sorunları
- Çözülen sorunlar
- Devam eden sorunlar
- Yeni keşfedilen URL'ler
- Kaldırılan veya artık keşfedilmeyen URL'ler
- HTTP durum kodu değişimleri
- Title değişimleri
- Meta description değişimleri
- Canonical değişimleri
- Indexability değişimleri
- Teknik SEO puanındaki değişim

Karşılaştırma yapılırken iki taramanın kapsam ve ayar farklılıkları dikkate alınmalıdır.

Bir URL'nin son taramada bulunmaması, kesin olarak silindiği anlamına gelmemelidir.

---

## 12. Raporlama ve Dışa Aktarma

Kapsamlı raporlama altyapısı geliştir.

### CSV raporları

- Tüm URL verileri
- HTTP durum kodları
- Meta bilgiler
- Heading bilgileri
- Görseller
- İç bağlantılar
- Dış bağlantılar
- SEO sorunları
- Yönlendirmeler
- Indexability sonuçları

Türkçe karakter desteği düzgün çalışmalıdır.

CSV formula injection gibi risklere karşı güvenli dışa aktarma uygulanmalıdır.

### HTML raporu

Tek dosyadan oluşan, kendi kendine yeterli bir HTML denetim raporu oluştur.

Raporda:

- Proje bilgileri
- Tarama tarihi
- Tarama ayarları ve kapsamı
- Genel teknik SEO puanı
- Özet istatistikler
- Sorunların önem derecesine göre dağılımı
- En önemli teknik problemler
- Etkilenen URL'ler
- Sorunların teknik kanıtları
- Çözüm önerileri
- Tarama sınırlamaları

yer almalıdır.

HTML raporu internet bağlantısı olmadan açılabilmelidir. Harici CDN, font veya JavaScript bağımlılığı olmamalıdır.

Rapor içindeki bütün kullanıcı ve site kaynaklı veriler güvenli biçimde escape edilmelidir.

### Yedekleme

Projeler, tarama verileri ve ayarlar kolayca yedeklenebilir ve geri yüklenebilir olmalıdır.

---

## 13. Veritabanı ve Veri Mimarisi

SQLite üzerinde düzenli ve normalize edilmiş bir veri mimarisi geliştir.

En azından aşağıdaki kavramları modelle:

- Projects
- CrawlJobs
- CrawlSettings
- Pages
- PageMetadata
- Links
- Images
- Redirects
- Issues
- CrawlSnapshots
- Reports

Gerektiğinde tablolar eklenebilir veya ilişkiler daha uygun biçimde yeniden tasarlanabilir.

Veri modeli aşağıdaki ihtiyaçları karşılamalıdır:

- Çoklu proje desteği
- Her proje için birden fazla tarama
- Geçmiş taramaların korunması
- URL tekrarlarının kontrolü
- Hızlı arama ve filtreleme
- Büyük URL listelerinde makul sorgu performansı
- Sorunların taramalar arasında karşılaştırılması

SQLite için uygun indeksler ve WAL modu kullan.

İşlem sırasında veri bütünlüğü korunmalıdır.

İç içe geçmiş büyük JSON alanlarına gereksiz bağımlılık oluşturma.

Veritabanı şeması için sürümlü migration sistemi kur.

---

## 14. Performans ve Kaynak Yönetimi

Tarama motoru verimli olmalıdır.

- Asenkron HTTP istekleri
- Kontrollü eşzamanlılık
- URL kuyruğu
- URL tekilleştirme
- Bellek kullanımını sınırlama
- Ağ zaman aşımı yönetimi
- Başarısız istekleri kontrollü yeniden deneme
- Kaynak tüketimi sınırları
- SQLite toplu yazma optimizasyonları
- Playwright tarayıcı havuzu yönetimi

HTML dosyaları, yanıt gövdeleri ve render süreleri için yapılandırılabilir üst sınırlar belirle.

Büyük dosyalar veya sonsuz yönlendirmeler uygulamanın kilitlenmesine neden olmamalıdır.

Aynı URL'nin farklı normalizasyon biçimleriyle gereksiz tekrar taranmasını engelle. Ancak teknik SEO açısından önemli URL farklılıklarını raporlamayı sürdür.

Performans hedefi olarak 1.000, 10.000 ve daha büyük URL kümelerine uygun mimari kur. Gerçek cihazda ölçülmeyen hız veya kapasite garantileri verme.

---

## 15. Hata Yönetimi

Aşağıdaki durumlar kontrollü şekilde ele alınmalıdır:

- İnternet bağlantısı olmaması
- DNS hataları
- SSL/TLS sertifika hataları
- Sunucu zaman aşımı
- robots.txt erişim sorunları
- HTTP 429
- HTTP 403
- Playwright başlatma hataları
- Geçersiz HTML
- Hatalı XML Sitemap
- SQLite bağlantı sorunları
- Disk dolması
- Taramanın kullanıcı tarafından durdurulması

Kullanıcıya yalnızca teknik hata kodları gösterilmemelidir.

Anlaşılır hata açıklamaları ve çözüm önerileri sunulmalıdır.

Hatalar yerel log dosyalarına kaydedilmelidir.

Gizli bilgiler loglarda tutulmamalıdır.

---

## 16. Güvenlik ve Gizlilik

Uygulama yerel kullanım esasına göre hazırlanmalıdır.

- Veriler varsayılan olarak kullanıcının bilgisayarında tutulmalıdır.
- Telemetri eklenmemelidir.
- Üçüncü taraf analiz servisleri kullanılmamalıdır.
- Kullanıcı hesapları veya bulut tabanlı oturum sistemi oluşturulmamalıdır.
- Gizli bilgiler `.env` dosyasında saklanmalıdır.
- `.env.example` dosyası hazırlanmalıdır.
- Gerçek şifreler veya kimlik bilgileri Git'e eklenmemelidir.
- API girişleri doğrulanmalıdır.
- SQL injection risklerine karşı parametrik sorgular kullanılmalıdır.
- XSS risklerine karşı güvenli şablon işleme uygulanmalıdır.
- Dışa aktarılan dosya adları güvenli oluşturulmalıdır.
- Yerel yönetim servisi varsayılan olarak yalnızca `127.0.0.1` adresini dinlemelidir.
- Hedef sitelerden dönen HTML güvenilmez veri olarak kabul edilmelidir.

Uygulama otomatik olarak üretim web sitelerinde değişiklik yapmamalıdır.

---

## 17. Mimari ve Kod Kalitesi

Profesyonel bir proje mimarisi oluştur.

Aşağıdaki sorumluluklar ayrı katmanlarda bulunmalıdır:

1. API ve HTTP route yönetimi
2. HTMX ve HTML arayüzleri
3. Tarama motoru
4. URL keşfi ve kuyruk yönetimi
5. HTML ayrıştırma
6. Teknik SEO analizleri
7. Sorun tespit kuralları
8. Veritabanı erişimi
9. Rapor oluşturma
10. Yapılandırma
11. Loglama
12. Testler

Kod tekrarını önle.

Her SEO analizi mümkün olduğunca bağımsız ve test edilebilir olmalıdır.

Yeni bir SEO kontrolü eklemek için bütün uygulamanın değiştirilmesi gerekmemelidir.

Python kodlarında mümkün olduğunca type hint kullan.

İş mantığı doğrudan HTML şablonlarına yazılmamalıdır.

---

## 18. Kurulum ve İlk Çalıştırma

Uygulama boş bir depodan kurulabilmelidir.

Python 3.12 ön koşulu kabul edilebilir.

Windows, Linux ve macOS için çalıştırma süreci belgelenmelidir.

İlk kullanım için tek komutlu bir başlangıç mekanizması oluştur.

Örneğin:

`python run.py`

Bu başlangıç mekanizması gerektiğinde:

- Sanal ortamı hazırlamalı
- Python bağımlılıklarını kurmalı
- Playwright için Chromium bağımlılığını hazırlamalı
- Veritabanını oluşturmalı veya migration uygulamalı
- Yerel FastAPI sunucusunu başlatmalı

Tekrarlanan çalıştırmalarda gereksiz kurulum işlemleri yapmamalıdır.

İlk kurulumun internet bağlantısı ve bazı işletim sistemi bağımlılıkları gerektirebileceğini README içerisinde açıkla.

Manuel kurulum komutlarını da belgele.

---

## 19. Testler ve Kalite Kontrolü

Pytest tabanlı test altyapısı oluştur.

Aşağıdaki testler bulunmalıdır:

- URL normalizasyonu
- Domain ve kapsam kontrolü
- robots.txt kuralları
- Canonical analizi
- Title ve description analizi
- Heading analizi
- Indexability hesaplaması
- Redirect zinciri tespiti
- Sorun önceliklendirmesi
- SEO sağlık puanı
- CSV raporu
- HTML raporu
- Veritabanı işlemleri

Bunlara ek olarak uçtan uca çalışan en az bir başarılı senaryo testi oluştur.

Testler üçüncü taraf canlı web sitelerine bağımlı olmamalıdır.

Yerel test web sitesi veya HTTP fixture'ları kullanılmalıdır.

Güvenlik sınırlarının aşılmadığını doğrulayan negatif testler de bulunmalıdır.

---

## 20. README ve Dokümantasyon

Kapsamlı bir README.md oluştur.

İçeriğinde:

- Projenin amacı
- Özellikler
- Teknoloji yığını
- Sistem gereksinimleri
- Kurulum
- İlk çalıştırma
- Proje mimarisi
- Veritabanı yapısı
- Tarama ve izin politikası
- Veri saklama konumu
- Yedekleme ve geri yükleme
- Test komutları
- Performans sınırları
- Bilinen eksikler
- Sorun giderme

bulunmalıdır.

Dokümantasyon Türkçe yazılmalıdır.

---

## 21. Bilinçli Olarak Kapsam Dışında Tutulacaklar

Aşağıdaki özellikleri ilk sürüme dahil etme:

- Kullanıcı hesap sistemi
- Ücretli abonelikler
- Ödeme altyapısı
- Bulut tabanlı kontrol paneli
- Telemetri
- Reklam
- İzin alınmamış sitelerin taranması
- Web ölçeğinde backlink veritabanı
- Web ölçeğinde anahtar kelime veritabanı
- Üretim sitelerinde otomatik SEO değişiklikleri
- Google Search Console bağlantısı olmadan gerçek indeks verisi iddiaları
- Gerçek saha verisi olmadan Core Web Vitals ölçümü iddiaları

Öncelik, güvenilir teknik SEO taraması ve raporlamadır.

---

## 22. Geliştirme Sırası

Projeyi aşağıdaki aşamalara göre geliştir:

**Aşama 1 — Temel altyapı**

- Proje yapısı
- Bağımlılıklar
- Veritabanı
- Konfigürasyon
- FastAPI
- HTMX temel arayüzü

**Aşama 2 — Tarama motoru**

- URL keşfi
- HTTP istekleri
- robots.txt
- Sitemap
- Kuyruk
- URL normalizasyonu
- Playwright render
- Tarama limitleri

**Aşama 3 — SEO analizleri**

- Meta etiketler
- Heading
- Canonical
- Indexability
- Dahili bağlantılar
- Görseller
- Structured Data
- Sorun tespit motoru

**Aşama 4 — Yönetim paneli**

- Dashboard
- Proje yönetimi
- Gerçek zamanlı ilerleme
- URL tabloları
- URL detayları
- SEO sorunları

**Aşama 5 — Raporlama ve geçmiş**

- CSV
- Bağımsız HTML raporu
- SEO sağlık puanı
- Tarama karşılaştırması
- Yedekleme

**Aşama 6 — Test ve son kontroller**

- Birim testleri
- Entegrasyon testleri
- Uçtan uca test
- Güvenlik testleri
- README
- Kurulum doğrulaması

---

## 23. Kabul Kriterleri

Proje ancak aşağıdaki koşullar karşılandığında tamamlanmış sayılabilir:

1. Uygulama yerel ortamda açılmalıdır.
2. Kullanıcı yeni bir web sitesi projesi oluşturabilmelidir.
3. Kullanıcı tarama ayarlarını değiştirebilmelidir.
4. Tarama başlamadan önce izin onayı alınmalıdır.
5. Tarama motoru gerçek bir izinli web sitesini tarayabilmelidir.
6. robots.txt ve URL kapsam kurallarına uyulmalıdır.
7. HTML ve gerektiğinde render edilmiş DOM analiz edilmelidir.
8. Tarama ilerlemesi arayüzden takip edilebilmelidir.
9. SEO sorunları gerçek verilerden üretilmelidir.
10. Sorunlar teknik kanıt ve çözüm önerileriyle listelenmelidir.
11. Her URL'nin detayları görüntülenebilmelidir.
12. CSV ve HTML raporları oluşturulabilmelidir.
13. Eski taramalar korunmalıdır.
14. İki tarama karşılaştırılabilmelidir.
15. Temel güvenlik önlemleri uygulanmalıdır.
16. Testler çalıştırılmış olmalıdır.
17. README eksiksiz olmalıdır.

---

## 24. Yapay Zekâ Geliştirme Ajanına Son Talimatlar

Bu projeyi yalnızca kavramsal olarak açıklama. Gerçekten geliştir.

Boş depoda ihtiyaç duyulan klasörleri ve dosyaları oluştur.

Eksik fonksiyonlar, sahte API sonuçları veya çalışmayan placeholder özelliklerle projeyi tamamlanmış gibi gösterme.

Kapsam büyük olduğu için önce bütün gereksinimleri karşılayabilecek sağlam bir mimari oluştur. Ardından gerçekten çalışan uçtan uca çekirdek iş akışını tamamla ve diğer modülleri bunun üzerine ekle.

Kodlar mümkün olduğunca temiz, modüler, tip güvenli ve sürdürülebilir olmalıdır.

Her önemli geliştirme aşamasından sonra mevcut kodu kontrol et.

Teknik SEO ile ilgili kararları gerçek standartlara ve açıkça tanımlanmış kurallara dayandır.

Belirsiz analiz sonuçlarını kesin gerçek olarak sunma.

Projenin sonunda:

- Gerçek test komutlarını çalıştır.
- Test sonuçlarını bildir.
- Başarısız test varsa açıkça belirt.
- Uygulamanın başlangıç komutunu göster.
- Tamamlanan özellikleri listele.
- Eksik veya sınırlı özellikleri açıkça belirt.
- Kullanılan önemli bağımlılıkları ve sürümlerini belgele.

**Sonuç, kullanıcıların gerçekten çalıştırabildiği, web sitelerinin teknik SEO durumunu analiz edebildiği ve profesyonel raporlar oluşturabildiği bir uygulama olmalıdır.**

---

## 25. Uygulama Adı ve Marka Kimliği

Uygulamanın resmî adı **Zerqon Spider** olacaktır.

Tüm proje boyunca bu isim tutarlı şekilde kullanılmalıdır.

- **Marka adı:** Zerqon
- **Ürün adı:** Zerqon Spider
- **Slogan:** Crawl Deeper. Discover More.
- **Ürün açıklaması:** Advanced SEO Crawler & Auditor
- **GitHub proje adı:** zerqon-spider

### Tasarım ve Marka Kimliği

- Modern, premium, güçlü ve teknolojik bir görsel kimlik oluştur.
- Ana renkler koyu lacivert, antrasit ve elektrik mavisi olsun.
- Açık ve koyu tema desteği sağla.
- Zerqon Spider için özgün, minimalist bir SVG logo tasarla.
- Logoda **Z harfi ile geometrik örümcek figürünü** birleştiren yaratıcı bir tasarım kullan.
- Uygulamaya özel favicon oluştur.
- Giriş ekranı, dashboard, raporlar ve uygulama başlığında marka kimliğini tutarlı kullan.
- Arayüz profesyonel bir masaüstü SEO analiz yazılımı hissi vermelidir.

Varsayılan arayüz dili Türkçe olmalıdır. İngilizce dil desteği korunmalıdır.

**Önemli:** Uygulama adı, sloganı ve görsel kimliği tüm ekranlarda, HTML raporlarında ve dokümantasyonda tutarlı kullanılmalıdır. Mevcut SEO tarama özelliklerinden veya performansından ödün verilmemelidir.

---

## Ek Talimatlar (Konuşma Sırasında)

- 2026-10-09: GitHub reposu **public** olacak. Her aşama commit'lenip push'lanacak.
- 2026-10-09: Commit'ler **Taha Furkan Bayar <tahafurkanbayar@gmail.com>** adına atılacak.
- 2026-10-09: Prompt ve ilerlemeler teknik olarak organize edilmiş md dosyalarında tutulacak (bkz. `docs/ai/`).
- 2026-10-09: Commit mesajlarına **Co-Authored-By / AI atıf satırı eklenmez**; commit'lerde yalnızca kullanıcı görünür.
