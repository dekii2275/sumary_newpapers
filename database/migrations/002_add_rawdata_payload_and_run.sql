BEGIN;

ALTER TABLE rawdata
    ADD COLUMN IF NOT EXISTS raw_payload_type VARCHAR(100);

ALTER TABLE rawdata
    ADD COLUMN IF NOT EXISTS crawl_run_id UUID;

-- Existing rows predate crawl_run_id. Give each legacy record its own run id
-- so the new NOT NULL contract can be applied without dropping data.
UPDATE rawdata
SET crawl_run_id = gen_random_uuid()
WHERE crawl_run_id IS NULL;

UPDATE rawdata
SET raw_payload_type = 'text/html'
WHERE raw_payload_type IS NULL
  AND raw_object_key IS NOT NULL;

ALTER TABLE rawdata
    ALTER COLUMN crawl_run_id SET DEFAULT gen_random_uuid(),
    ALTER COLUMN crawl_run_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rawdata_crawl_run_id
    ON rawdata (crawl_run_id);

COMMIT;
