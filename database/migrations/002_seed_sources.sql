BEGIN;

INSERT INTO sources (name, url, source_type, is_active)
VALUES 
    ('vnexpress', 'https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss', 'rss', TRUE),
    ('vienamnet', 'https://vietnamnet.vn/cong-nghe.rss', 'rss', TRUE),
    ('tuoitre', 'https://tuoitre.vn/rss/khoa-hoc.rss', 'rss', TRUE)
ON CONFLICT (url) DO UPDATE SET
    name = EXCLUDED.name,
    source_type = EXCLUDED.source_type,
    is_active = EXCLUDED.is_active;

COMMIT;
