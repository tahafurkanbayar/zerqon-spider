-- Tarama sırasında oluşan, kullanıcıya gösterilecek olaylar (robots erişilemedi, sitemap hatası,
-- render kullanılamıyor, sunucu yavaşlama istedi vb.). Metinler i18n'de `events.<code>` altındadır.
CREATE TABLE crawl_events (
    id          INTEGER PRIMARY KEY,
    crawl_id    INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    level       TEXT    NOT NULL CHECK (level IN ('info', 'warning', 'error')),
    code        TEXT    NOT NULL,
    detail      TEXT
);
CREATE INDEX ix_crawl_events_crawl ON crawl_events(crawl_id, id);

-- X-Robots-Tag ve meta robots kaynaklı nofollow bilgisi analizde ayrı tutulur
ALTER TABLE pages ADD COLUMN page_nofollow INTEGER NOT NULL DEFAULT 0;
-- Sayfanın neden JavaScript ile render edildiği (javascript modu, hibrit tetikleyici adı)
ALTER TABLE pages ADD COLUMN render_reason TEXT;
