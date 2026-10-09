# Zerqon Spider — AI Asistan Talimatları

Bu repoda çalışmaya başlamadan önce sırayla oku:
1. `docs/ai/CONTEXT.md` — şu anki durum, komutlar, sıradaki adım
2. `docs/ai/ROADMAP.md` — kalan işler ve kabul kriterleri
3. Gerekirse `docs/ai/DECISIONS.md` (mimari kararlar) ve `docs/ai/PROMPT.md` (orijinal gereksinim, değiştirilmez)

Kurallar:
- Her anlamlı adımda: testleri çalıştır → `docs/ai/PROGRESS.md` + `ROADMAP.md` + `CONTEXT.md` güncelle → commit → push.
- Commit yazarı repo-yerel git config'tedir (Taha Furkan Bayar); değiştirme. Commit mesajlarına Co-Authored-By veya AI atıf satırı EKLENMEZ.
- Python: `.venv/Scripts/python` (3.12). Sistem Python'u (3.15) kullanma.
- UI metni sadece `zerqon/i18n/locales/{tr,en}.json` içinde; iki dosyanın anahtarları eşit olmalı (test var).
- Sahte veri/placeholder özellik ekleme; kısıtları README "Bilinen eksikler" bölümüne yaz.
