# Zerqon Spider — Teknik SEO Sağlık Puanı ve Önceliklendirme

> **Önemli:** Bu puan Zerqon Spider'ın kendi, belgelenmiş ve deterministik modelidir.
> Google'ın veya başka bir arama motorunun resmi değerlendirmesi **değildir**; sıralama garantisi vermez.
> Kaynak kod: `zerqon/analysis/scoring.py`, `zerqon/analysis/prioritization.py`.

## 1. Önceliklendirme (sorun önem seviyeleri)

Her sorun kodunun registry'de bir **temel önemi** vardır (`zerqon/analysis/issues.py`).
Tarama sonunda her sorun kaydının **nihai önemi** aşağıdaki kurallarla, her seferinde temel önemden başlanarak hesaplanır:

| # | Kural | Etki |
|---|---|---|
| 1 | `status_5xx` / `fetch_error` analiz edilen URL'lerin ≥%10'unu **veya** ≥10 URL'yi etkiliyor | **Kritik** |
| 2 | `status_4xx` / `broken_internal_link` etkilenen oran ≥%10 | Bir seviye yükselir |
| 3 | Sayfa önemli (başlangıç sayfası, sitemap'te veya gelen bağlantı ≥ max(10, ilk %10 eşiği)) ve kod önem-duyarlı | Bir seviye yükselir; önemli sayfada `noindex` → **Yüksek** ("muhtemelen istenmeyen noindex") |
| 4 | Title/description/başlık/içerik/sosyal/görsel kategorisi + sayfa indexlenemez | Bir seviye düşer |
| 5 | Şablon geneli: düşük seviyeli meta/içerik sorunu indexlenebilir sayfaların ≥%50'sinde (en az 5) | **Orta** |

`priority_score` (sıralama için): `(6 − seviye_sırası) × 20 + min(20, 4 × log2(1 + gelen_bağlantı)) + 5 × sitemap'te_mi`.

## 2. Sağlık puanı

```
puan = 100 × Π  (1 − w[önem] × √oran)
        (kod, önem)

w = { kritik: 0.25, yüksek: 0.12, orta: 0.05, düşük: 0.015, bilgi: 0 }
oran = etkilenen URL sayısı / analiz edilen URL sayısı   (site geneli sorunlarda oran = 1)
analiz edilen URL = HTML sayfalar + 4xx/5xx/bağlantı hatası veren URL'ler
```

Özellikler:
- **Deterministik:** aynı veri her zaman aynı puanı verir.
- **Sınırlı:** çarpım modeli puanı 0–100 aralığında tutar.
- **Yaygınlığa duyarlı:** karekök sayesinde tek bir sayfadaki kritik sorun da görünür etki yapar, ancak tüm siteyi etkileyen sorun daha ağır cezalandırılır.
- **Kategori alt puanları:** aynı formül her kategori için ayrı uygulanır (`score_breakdown`).

Örnek: 100 sayfalık sitede 10 sayfa 5xx (nihai önem kritik): `1 − 0.25 × √0.1 = 0.921` → 92,1.
Ek olarak tüm sayfalarda meta description eksik (şablon geneli → orta): `× (1 − 0.05 × 1) = 0.95` → 87,5.

## 3. Güvenilirlik

Puanın ne kadar temsil edici olduğunu gösterir. Nedenler ve ağırlıkları:

| Neden | Ağırlık |
|---|---|
| `partial_crawl` — tarama durduruldu / yarım kaldı / başarısız | 2 |
| `url_limit` — URL limitine ulaşıldı (site tamamı taranmamış olabilir) | 1 |
| `very_few_pages` — 3'ten az HTML sayfa | 2 |
| `few_pages` — 10'dan az HTML sayfa | 1 |
| `many_errors` — URL'lerin %20'sinden fazlası hata | 1 |
| `robots_blocked` — URL'lerin %30'undan fazlası robots.txt ile engelli | 1 |
| `robots_unavailable` — robots.txt erişilemedi | 2 |
| `no_html` — hiç HTML sayfa analiz edilemedi | 3 |

Toplam 0 → **yüksek**, 1–2 → **orta**, ≥3 → **düşük**.

## 4. Taramalar arası karşılaştırma

Puan farkı gösterilirken iki taramanın ayar farkları (URL limiti, derinlik, render modu, kapsam kuralları,
eşikler) ve tamamlanma durumları uyarı olarak listelenir. Bir URL'nin yeni taramada bulunmaması,
**silindiği anlamına gelmez** ("artık keşfedilmedi").
