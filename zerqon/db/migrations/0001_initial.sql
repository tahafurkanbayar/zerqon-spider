-- Zerqon Spider — başlangıç şeması
-- Not: Tüm zaman damgaları ISO-8601 UTC metin olarak saklanır.

CREATE TABLE crawl_settings (
    id                      INTEGER PRIMARY KEY,
    max_urls                INTEGER NOT NULL DEFAULT 500,
    max_depth               INTEGER NOT NULL DEFAULT 10,
    concurrency             INTEGER NOT NULL DEFAULT 4,
    delay_ms                INTEGER NOT NULL DEFAULT 250,
    timeout_seconds         REAL    NOT NULL DEFAULT 20,
    max_retries             INTEGER NOT NULL DEFAULT 2,
    user_agent              TEXT    NOT NULL,
    include_subdomains      INTEGER NOT NULL DEFAULT 0,
    include_patterns        TEXT    NOT NULL DEFAULT '',
    exclude_patterns        TEXT    NOT NULL DEFAULT '',
    render_mode             TEXT    NOT NULL DEFAULT 'standard'
                            CHECK (render_mode IN ('standard', 'javascript', 'hybrid')),
    max_render_pages        INTEGER NOT NULL DEFAULT 200,
    use_sitemaps            INTEGER NOT NULL DEFAULT 1,
    check_images            INTEGER NOT NULL DEFAULT 1,
    allow_localhost         INTEGER NOT NULL DEFAULT 0,
    -- Analiz eşikleri (yapılandırılabilir, arama motoru kuralı değildir)
    title_min_chars         INTEGER NOT NULL DEFAULT 30,
    title_max_chars         INTEGER NOT NULL DEFAULT 60,
    description_min_chars   INTEGER NOT NULL DEFAULT 70,
    description_max_chars   INTEGER NOT NULL DEFAULT 160,
    min_word_count          INTEGER NOT NULL DEFAULT 200,
    max_url_length          INTEGER NOT NULL DEFAULT 115,
    large_image_bytes       INTEGER NOT NULL DEFAULT 204800,
    deep_page_depth         INTEGER NOT NULL DEFAULT 4,
    created_at              TEXT    NOT NULL
);

CREATE TABLE projects (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    start_url       TEXT    NOT NULL,
    settings_id     INTEGER NOT NULL REFERENCES crawl_settings(id),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    last_crawl_at   TEXT
);

CREATE TABLE crawl_jobs (
    id                       INTEGER PRIMARY KEY,
    project_id               INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    settings_id              INTEGER NOT NULL REFERENCES crawl_settings(id),
    start_url                TEXT    NOT NULL,
    status                   TEXT    NOT NULL DEFAULT 'queued'
                             CHECK (status IN ('queued', 'running', 'stopping', 'cancelled',
                                               'completed', 'failed', 'interrupted')),
    permission_confirmed     INTEGER NOT NULL CHECK (permission_confirmed = 1),
    permission_confirmed_at  TEXT    NOT NULL,
    created_at               TEXT    NOT NULL,
    started_at               TEXT,
    finished_at              TEXT,
    heartbeat_at             TEXT,
    urls_crawled             INTEGER NOT NULL DEFAULT 0,
    urls_failed              INTEGER NOT NULL DEFAULT 0,
    urls_queued              INTEGER NOT NULL DEFAULT 0,
    urls_discovered          INTEGER NOT NULL DEFAULT 0,
    limit_reached            INTEGER NOT NULL DEFAULT 0,
    resume_count             INTEGER NOT NULL DEFAULT 0,
    last_url                 TEXT,
    robots_status            TEXT,
    robots_url               TEXT,
    error_code               TEXT,
    error_message            TEXT
);
CREATE INDEX ix_crawl_jobs_project ON crawl_jobs(project_id, id DESC);
CREATE INDEX ix_crawl_jobs_status ON crawl_jobs(status);

-- Keşfedilen URL kuyruğu = checkpoint
CREATE TABLE frontier (
    id          INTEGER PRIMARY KEY,
    crawl_id    INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    url_key     TEXT    NOT NULL,
    depth       INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'skipped')),
    UNIQUE (crawl_id, url_key)
);
CREATE INDEX ix_frontier_pending ON frontier(crawl_id, status, depth, id);

CREATE TABLE pages (
    id                   INTEGER PRIMARY KEY,
    crawl_id             INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    url                  TEXT    NOT NULL,
    url_key              TEXT    NOT NULL,
    source               TEXT    NOT NULL,
    discovery_depth      INTEGER NOT NULL,
    crawl_depth          INTEGER,
    fetch_status         TEXT    NOT NULL
                         CHECK (fetch_status IN ('ok', 'error', 'blocked_robots', 'blocked_security', 'skipped')),
    status_code          INTEGER,
    content_type         TEXT,
    content_length       INTEGER,
    response_time_ms     INTEGER,
    fetched_at           TEXT    NOT NULL,
    is_html              INTEGER NOT NULL DEFAULT 0,
    body_truncated       INTEGER NOT NULL DEFAULT 0,
    redirect_url         TEXT,
    redirect_type        TEXT,
    error_code           TEXT,
    error_detail         TEXT,
    x_robots_tag         TEXT,
    crawlable            INTEGER NOT NULL DEFAULT 1,
    indexability         TEXT,
    indexability_reason  TEXT,
    in_sitemap           INTEGER NOT NULL DEFAULT 0,
    inlinks              INTEGER NOT NULL DEFAULT 0,
    unique_inlinks       INTEGER NOT NULL DEFAULT 0,
    outlinks_internal    INTEGER NOT NULL DEFAULT 0,
    outlinks_external    INTEGER NOT NULL DEFAULT 0,
    word_count           INTEGER,
    text_hash            TEXT,
    simhash              INTEGER,
    rendered             INTEGER NOT NULL DEFAULT 0,
    url_length           INTEGER NOT NULL,
    issues_count         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (crawl_id, url_key)
);
CREATE INDEX ix_pages_status ON pages(crawl_id, status_code);
CREATE INDEX ix_pages_indexability ON pages(crawl_id, indexability);
CREATE INDEX ix_pages_fetch ON pages(crawl_id, fetch_status);
CREATE INDEX ix_pages_text_hash ON pages(crawl_id, text_hash);

CREATE TABLE page_metadata (
    page_id                 INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
    title                   TEXT,
    title_count             INTEGER NOT NULL DEFAULT 0,
    title_length            INTEGER,
    meta_description        TEXT,
    description_count       INTEGER NOT NULL DEFAULT 0,
    description_length      INTEGER,
    meta_robots             TEXT,
    canonical               TEXT,
    canonical_key           TEXT,
    canonical_count         INTEGER NOT NULL DEFAULT 0,
    canonical_raw           TEXT,
    h1                      TEXT,
    h1_count                INTEGER NOT NULL DEFAULT 0,
    h2_count                INTEGER NOT NULL DEFAULT 0,
    lang                    TEXT,
    charset                 TEXT,
    viewport                TEXT,
    meta_refresh            TEXT,
    og_title                TEXT,
    og_description          TEXT,
    og_image                TEXT,
    og_url                  TEXT,
    og_type                 TEXT,
    twitter_card            TEXT,
    twitter_title           TEXT,
    twitter_description     TEXT,
    twitter_image           TEXT,
    hreflang_count          INTEGER NOT NULL DEFAULT 0,
    structured_data_count   INTEGER NOT NULL DEFAULT 0,
    -- Ham HTML ve render DOM karşılaştırması
    raw_title               TEXT,
    rendered_title          TEXT,
    raw_h1                  TEXT,
    rendered_h1             TEXT,
    raw_canonical           TEXT,
    rendered_canonical      TEXT,
    raw_meta_robots         TEXT,
    rendered_meta_robots    TEXT,
    raw_word_count          INTEGER,
    rendered_word_count     INTEGER,
    raw_link_count          INTEGER,
    rendered_link_count     INTEGER,
    render_only_links       INTEGER,
    render_error            TEXT
);
CREATE INDEX ix_meta_title ON page_metadata(title);
CREATE INDEX ix_meta_description ON page_metadata(meta_description);
CREATE INDEX ix_meta_h1 ON page_metadata(h1);

CREATE TABLE headings (
    id        INTEGER PRIMARY KEY,
    page_id   INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,
    level     INTEGER NOT NULL CHECK (level BETWEEN 1 AND 6),
    text      TEXT    NOT NULL
);
CREATE INDEX ix_headings_page ON headings(page_id, position);

CREATE TABLE links (
    id              INTEGER PRIMARY KEY,
    crawl_id        INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    source_page_id  INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    target_url      TEXT    NOT NULL,
    target_key      TEXT    NOT NULL,
    anchor_text     TEXT,
    rel             TEXT,
    nofollow        INTEGER NOT NULL DEFAULT 0,
    is_internal     INTEGER NOT NULL,
    render_only     INTEGER NOT NULL DEFAULT 0,
    position        INTEGER NOT NULL
);
CREATE INDEX ix_links_target ON links(crawl_id, target_key);
CREATE INDEX ix_links_source ON links(source_page_id);

CREATE TABLE images (
    id           INTEGER PRIMARY KEY,
    crawl_id     INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    page_id      INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    src          TEXT    NOT NULL,
    src_key      TEXT    NOT NULL,
    alt          TEXT,
    alt_present  INTEGER NOT NULL,
    width        TEXT,
    height       TEXT,
    loading      TEXT,
    has_srcset   INTEGER NOT NULL DEFAULT 0,
    is_internal  INTEGER NOT NULL,
    decorative   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_images_page ON images(page_id);
CREATE INDEX ix_images_src ON images(crawl_id, src_key);

-- Benzersiz görsel kaynaklarının HTTP kontrolü
CREATE TABLE image_resources (
    id            INTEGER PRIMARY KEY,
    crawl_id      INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    url           TEXT    NOT NULL,
    src_key       TEXT    NOT NULL,
    status_code   INTEGER,
    content_type  TEXT,
    size_bytes    INTEGER,
    error_code    TEXT,
    UNIQUE (crawl_id, src_key)
);

CREATE TABLE redirects (
    id           INTEGER PRIMARY KEY,
    crawl_id     INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    page_id      INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    hop          INTEGER NOT NULL,
    from_url     TEXT    NOT NULL,
    to_url       TEXT    NOT NULL,
    status_code  INTEGER,
    redirect_type TEXT
);
CREATE INDEX ix_redirects_page ON redirects(page_id, hop);
CREATE INDEX ix_redirects_crawl ON redirects(crawl_id);

CREATE TABLE hreflang (
    id        INTEGER PRIMARY KEY,
    page_id   INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    lang      TEXT    NOT NULL,
    href      TEXT    NOT NULL,
    href_key  TEXT    NOT NULL
);
CREATE INDEX ix_hreflang_page ON hreflang(page_id);
CREATE INDEX ix_hreflang_href ON hreflang(href_key);

CREATE TABLE structured_data (
    id              INTEGER PRIMARY KEY,
    page_id         INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    format          TEXT    NOT NULL CHECK (format IN ('json-ld', 'microdata', 'rdfa')),
    schema_type     TEXT,
    valid           INTEGER NOT NULL DEFAULT 1,
    error           TEXT,
    missing_fields  TEXT
);
CREATE INDEX ix_sd_page ON structured_data(page_id);

CREATE TABLE sitemaps (
    id            INTEGER PRIMARY KEY,
    crawl_id      INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    url           TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    parent_url    TEXT,
    status_code   INTEGER,
    kind          TEXT,
    url_count     INTEGER NOT NULL DEFAULT 0,
    error_code    TEXT,
    error_detail  TEXT
);
CREATE INDEX ix_sitemaps_crawl ON sitemaps(crawl_id);

CREATE TABLE sitemap_urls (
    id          INTEGER PRIMARY KEY,
    crawl_id    INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    sitemap_id  INTEGER NOT NULL REFERENCES sitemaps(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    url_key     TEXT    NOT NULL,
    lastmod     TEXT,
    UNIQUE (crawl_id, url_key)
);

CREATE TABLE issues (
    id              INTEGER PRIMARY KEY,
    crawl_id        INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    page_id         INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    url             TEXT,
    url_key         TEXT,
    code            TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    base_severity   TEXT    NOT NULL,
    severity        TEXT    NOT NULL,
    severity_rank   INTEGER NOT NULL,
    priority_score  REAL    NOT NULL DEFAULT 0,
    evidence        TEXT,
    signals         TEXT,
    detected_at     TEXT    NOT NULL
);
CREATE INDEX ix_issues_crawl_code ON issues(crawl_id, code);
CREATE INDEX ix_issues_crawl_sev ON issues(crawl_id, severity_rank);
CREATE INDEX ix_issues_page ON issues(page_id);
CREATE INDEX ix_issues_compare ON issues(crawl_id, code, url_key);

-- Tarama sonu özet (dashboard ve karşılaştırma için hızlı erişim)
CREATE TABLE crawl_snapshots (
    crawl_id            INTEGER PRIMARY KEY REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    computed_at         TEXT    NOT NULL,
    pages_total         INTEGER NOT NULL DEFAULT 0,
    pages_html          INTEGER NOT NULL DEFAULT 0,
    pages_failed        INTEGER NOT NULL DEFAULT 0,
    status_2xx          INTEGER NOT NULL DEFAULT 0,
    status_3xx          INTEGER NOT NULL DEFAULT 0,
    status_4xx          INTEGER NOT NULL DEFAULT 0,
    status_5xx          INTEGER NOT NULL DEFAULT 0,
    status_other        INTEGER NOT NULL DEFAULT 0,
    blocked_robots      INTEGER NOT NULL DEFAULT 0,
    indexable           INTEGER NOT NULL DEFAULT 0,
    non_indexable       INTEGER NOT NULL DEFAULT 0,
    avg_response_ms     REAL,
    issues_critical     INTEGER NOT NULL DEFAULT 0,
    issues_high         INTEGER NOT NULL DEFAULT 0,
    issues_medium       INTEGER NOT NULL DEFAULT 0,
    issues_low          INTEGER NOT NULL DEFAULT 0,
    issues_info         INTEGER NOT NULL DEFAULT 0,
    health_score        REAL,
    score_confidence    TEXT,
    confidence_reasons  TEXT,
    score_breakdown     TEXT
);

CREATE TABLE reports (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    crawl_id    INTEGER REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,
    filename    TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);
CREATE INDEX ix_reports_project ON reports(project_id, id DESC);

CREATE TABLE app_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
