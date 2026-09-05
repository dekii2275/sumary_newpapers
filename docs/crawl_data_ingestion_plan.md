# Crawl / Data Ingestion Implementation Plan

## Scope and status

This document was originally a plan only. Step 1 has now been implemented
without creating new database tables, changing Docker, or deleting existing
artifacts. Steps 2–5 remain planning scope.

## Implementation status

- Step 1 — **IMPLEMENTED** on 2026-08-26.
- Step 2 — pending; RSS/source discovery is not included in this batch.
- Step 3 — pending; HTTP-first/raw_documents/articles are not included.
- Step 4 — pending; multi-source reliability is not included.
- Step 5 — pending; production storage/scaling is not included.

The implementation details and verification results are reported in the
assistant handoff for this change. The remainder of this document preserves
the original design plan and acceptance criteria for the later steps.

The current repository is at a single-source crawler MVP:

    Manual URL
        -> Airflow
        -> Selenium
        -> VnExpress parser
        -> Local raw storage
        -> PostgreSQL rawdata

The target for this plan is Crawl/Data Ingestion V1:

    Sources
        -> Source feeds
        -> Discovery
        -> URL normalization and deduplication
        -> Crawl items
        -> HTTP fetch
        -> Browser fallback
        -> Raw documents
        -> Parser and validation
        -> Articles

NLP, summarization, embeddings, vector search, RAG, and video generation are
outside the scope of this plan.

## 1. Executive summary

The existing crawler is suitable for a small Step 1 experiment, but it is not
yet a reliable multi-source ingestion foundation.

The most urgent issues are:

- CRAWL_URLS is empty while the Airflow DAG is unpaused.
- Airflow retries the whole URL batch instead of the failed URL.
- raw_content_hash is stored but is not used for deduplication.
- Metadata JSON exists in old and new formats.
- Raw artifacts can be created without a database row if the DB insert fails.
- http_status is not actually captured by the Selenium fetcher.
- There is no source registry, RSS discovery, crawl_items, raw_documents, or
  articles table.
- There are no crawler/parser tests.

The implementation should proceed in five steps:

1. Stabilize the current manual crawler.
2. Add sources, feeds, and RSS discovery.
3. Add HTTP-first fetching, browser fallback, raw_documents, and articles.
4. Add reliability controls and a second source.
5. Productionize storage, monitoring, retention, and scaling decisions.

## 2. Current state verification

| Area | Status | Evidence |
| --- | --- | --- |
| Manual URL input | CONFIRMED | airflow/dags/crawl_vnexpress.py, _configured_urls |
| Empty CRAWL_URLS in local config | CONFIRMED | .env currently has CRAWL_URLS= |
| Fail-fast behavior for empty URL list | CONFIRMED | airflow/dags/crawl_vnexpress.py, run_crawler_batch |
| Six-hour schedule | CONFIRMED | airflow/dags/crawl_vnexpress.py, DAG schedule |
| Whole-batch Airflow retry | CONFIRMED | Airflow retries the PythonOperator task |
| One browser reused for a batch | CONFIRMED | airflow/dags/crawl_vnexpress.py |
| Selenium as the primary fetcher | CONFIRMED | scripts/crawl_to_db.py, SeleniumFetcher |
| HTTP fetcher | NOT PRESENT | No requests/httpx fetch implementation |
| VnExpress-specific parser | CONFIRMED | scripts/crawl_to_db.py, VnExpressParser |
| RSS, sitemap, or category discovery | NOT PRESENT | No discovery implementation found |
| URL normalization | CONFIRMED, BASIC | scripts/crawl_to_db.py, normalize_url |
| URL deduplication | NOT PRESENT | No lookup or unique constraint |
| Raw HTML gzip storage | CONFIRMED | scripts/crawl_to_db.py, save_artifacts |
| Local filesystem storage | CONFIRMED | crawl_data and docker-compose volume |
| MinIO/S3 | NOT PRESENT | Only described as a future target |
| PostgreSQL rawdata table | CONFIRMED | database/init/001_create_rawdata.sql |
| sources/source_feeds/crawl_runs/crawl_items | NOT PRESENT | No corresponding tables |
| raw_documents/articles | NOT PRESENT | No corresponding tables |
| Redis/Celery | NOT PRESENT | Not in Docker Compose |
| Crawler/parser tests | NOT PRESENT | No test files found |
| Article backend API | NOT PRESENT | backend/app.py only exposes health/db-check |

Runtime checks confirmed:

- Airflow webserver and scheduler are running.
- CRAWL_URLS is empty inside the Airflow container.
- The DAG is unpaused.
- PostgreSQL rawdata contains one successful record, one distinct URL, and one
  crawl run.
- crawl_data contains two raw/metadata artifact pairs.
- The artifacts use both the old raw_html_path/crawl_status format and the new
  raw_object_key/status format.

The current database row has a matching raw artifact. The older artifact pair
is not referenced by the current database row and should be treated as legacy
inventory until it is reconciled.

## 3. Step 1 — Stabilize current crawler

### Goal

Make the current VnExpress crawler reliable without replacing the existing
architecture. Keep manual URL mode, Selenium, the current parser, local raw
storage, and rawdata while fixing configuration, metadata, idempotency, and
tests.

### Current state

Existing components:

- airflow/dags/crawl_vnexpress.py
- scripts/crawl_to_db.py
- database/init/001_create_rawdata.sql
- database/migrations/002_add_rawdata_payload_and_run.sql
- crawl_data/

### Task 1.1 — Configuration guard and manual mode

Files/modules:

- CHANGE: airflow/dags/crawl_vnexpress.py
- CHANGE: .env.example
- CHANGE: docs/airflow.md
- NEW: tests/unit/test_dag_config.py

Database impact:

- NONE.

Implementation:

- Keep CRAWL_URLS as an explicit debug/manual mode.
- Keep a clear failure message when manual execution has no URLs.
- Do not allow an unconfigured scheduled run to appear healthy.
- Document that manual URL input is temporary and not the production flow.

Dependencies:

- Depends on: none.
- Blocks: Task 1.4.

Tests and acceptance:

- Empty URL list is handled explicitly.
- One URL and multiple URLs are parsed correctly.
- Whitespace and duplicate inputs are handled.
- Configuration behavior is documented consistently.

### Task 1.2 — Canonical metadata contract

Files/modules:

- CHANGE: scripts/crawl_to_db.py
- CHANGE: docs/airflow.md
- CHANGE: docs/step_01_news_article_crawler.md
- NEW: tests/fixtures/metadata/v2_success.json
- NEW: tests/unit/test_metadata_schema.py
- DEPRECATE: raw_html_path and crawl_status for newly created metadata.

Database impact:

- No immediate table change.
- A compatibility migration may be designed after the legacy artifacts are
  inventoried.

Implementation:

New metadata should use one schema containing:

- schema_version
- source
- url
- final_url
- title
- author
- published_at
- content
- thumbnail_url
- raw_object_key
- raw_payload_type
- raw_content_hash
- status
- http_status
- crawl_run_id
- fetched_at

Existing files should not be rewritten blindly. Legacy files should be
identified as version 1 and handled by a compatibility reader or a later
backfill.

Dependencies:

- Depends on: Task 1.1.
- Blocks: Task 1.3 and Step 3.

Tests and acceptance:

- Successful metadata validates.
- Optional author and published_at fields can be null.
- Failed metadata validates.
- Legacy metadata is not confused with the new schema.

### Task 1.3 — URL normalization, idempotency, and artifact consistency

Files/modules:

- CHANGE: scripts/crawl_to_db.py
- CHANGE: airflow/dags/crawl_vnexpress.py
- NEW: scripts/reconcile_crawl_artifacts.py
- NEW: tests/unit/test_url_normalization.py
- NEW: tests/integration/test_retry_idempotency.py

Database impact:

- Planned migration only.
- Preflight duplicate data before adding a unique constraint.
- Add a safe uniqueness rule for source_id, crawl_run_id, and normalized URL.

Implementation:

Normalization should address:

- tracking parameters;
- fragments;
- hostname casing;
- default ports;
- safe trailing-slash behavior.

Do not remove a meaningful path slash without source-specific evidence.

The crawl_run_id must remain stable across retries of the same Airflow DagRun.
It should not be generated afresh inside each retry attempt. A deterministic
identifier derived from the DagRun identity is preferable.

The raw artifact should be written through a temporary file and atomically
renamed before the database reference is committed. A reconciliation command
must detect:

- raw file exists but database row is missing;
- database row exists but raw file is missing;
- hash mismatch;
- legacy metadata without a database reference.

Dependencies:

- Depends on: Task 1.2.
- Blocks: Step 2.

Tests and acceptance:

- Tracking URLs normalize consistently.
- Duplicate URLs do not create duplicate records within a run.
- Retrying a run does not duplicate successful URLs.
- Artifact and database references can be reconciled.

### Task 1.4 — Regression tests and baseline crawl

Files/modules:

- NEW: tests/fixtures/vnexpress/normal.html
- NEW: tests/fixtures/vnexpress/missing_author.html
- NEW: tests/fixtures/vnexpress/no_content.html
- NEW: tests/fixtures/vnexpress/blocked.html
- NEW: tests/unit/test_vnexpress_parser.py
- NEW: tests/integration/test_local_storage.py

Database impact:

- Use a separate test database for integration tests.

Implementation:

Unit tests must use local HTML fixtures. A live crawl of 20–50 articles is a
separate opt-in smoke/regression test.

Dependencies:

- Depends on: Tasks 1.1, 1.2, and 1.3.
- Blocks: Step 2.

Tests and acceptance:

- Valid article.
- Missing author.
- Missing published time.
- Empty HTML.
- Missing content.
- Invalid URL.
- Timeout.
- One failed URL does not stop the next URL.
- Retry does not create duplicate data.

### Step 1 Definition of Done

**Status: implemented.** The baseline crawl and reconciliation findings are
documented separately because existing legacy artifacts are intentionally not
rewritten or deleted.

- Manual execution is explicit and does not produce meaningless scheduled
  failures.
- New metadata uses one schema with schema_version.
- Existing artifacts are not deleted.
- Retry does not create duplicates.
- One failed URL does not stop subsequent URLs.
- Parser, storage, URL normalization, and retry tests exist.
- A 20–50 article baseline can be measured.
- Artifact/database reconciliation is available.

## 4. Step 2 — Sources, feeds, and discovery

### Goal

Remove manual URL input from normal operation. Use VnExpress RSS as the first
discovery source and persist discovered URLs as crawl items.

### Current state

There is no source registry, feed registry, RSS parser, discovery DAG, or
crawl_items table. source_id=1 and source_name=vnexpress are currently
configuration values.

### Task 2.1 — Source, feed, run, and item schema

Files/modules:

- NEW: database/migrations/003_sources_and_discovery.sql
- NEW: crawler/models/source.py
- NEW: crawler/models/crawl_run.py
- NEW: crawler/models/crawl_item.py
- CHANGE: database/init/
- CHANGE: .env.example

Database impact:

Create:

- sources
- source_feeds
- crawl_runs
- crawl_items

Minimum fields:

sources:

- id
- name
- source_type
- base_url
- is_active
- config_json
- created_at

source_feeds:

- id
- source_id
- feed_type
- url
- is_active
- last_success_at

crawl_runs:

- id
- source_id
- trigger_type
- status
- started_at
- finished_at

crawl_items:

- id
- source_id
- normalized_url
- status
- first_discovered_at
- last_discovered_at
- last_crawl_run_id
- attempt_count
- last_error_type
- last_error_message

Initial constraints:

- unique source name;
- unique source/feed URL;
- unique source/normalized URL for the persistent crawl-item registry.

Dependencies:

- Depends on: Step 1.
- Blocks: Task 2.3.

Tests and acceptance:

- VnExpress source can be seeded.
- Duplicate source/feed/item is rejected or upserted safely.
- Disabled source/feed is not processed.

### Task 2.2 — RSS discovery adapter

Files/modules:

- NEW: crawler/discovery/base.py
- NEW: crawler/discovery/rss.py
- NEW: tests/fixtures/rss/vnexpress.xml
- NEW: tests/unit/test_rss_discovery.py
- CHANGE: scripts/requirements.txt
- CHANGE: airflow/Dockerfile if a new dependency is required.

Database impact:

- Reads source_feeds.
- Upserts crawl_items.

Implementation:

RSS discovery should:

- fetch the feed;
- parse item links;
- normalize URLs;
- filter article URLs;
- upsert crawl_items;
- record feed errors and timestamps.

Only RSS is required at this stage. Sitemap, category, and API discovery can
follow later.

Dependencies:

- Depends on: Task 1.3 and Task 2.1.
- Can run in parallel with Task 2.1 after the URL contract is fixed.
- Blocks: Task 2.3.

Tests and acceptance:

- Valid RSS fixture.
- Empty feed.
- Malformed feed.
- Duplicate links.
- Tracking links.
- Non-article links.
- Feed timeout.

### Task 2.3 — Discovery orchestration

Files/modules:

- CHANGE: airflow/dags/crawl_vnexpress.py
- NEW: airflow/dags/discover_vnexpress.py
- NEW: crawler/repositories/crawl_items.py

Database impact:

- Writes crawl_runs and crawl_items.

Implementation:

The first version can use Airflow tasks:

    discover_rss
        -> select queued crawl_items
        -> pass item IDs to crawl tasks

Manual URL input remains available as a debug path.

Dependencies:

- Depends on Tasks 2.1 and 2.2.
- Blocks Step 3.

Tests and acceptance:

- Discovery creates a crawl run.
- New URLs create crawl items.
- Existing URLs are updated rather than duplicated.
- A failed feed does not delete existing items.
- Normal operation does not require CRAWL_URLS.

### Task 2.4 — Discovery observability

Files/modules:

- CHANGE: docs/airflow.md
- NEW: crawler/observability/discovery_metrics.py

Database impact:

- Use crawl_runs counters initially.
- Do not require Prometheus yet.

Minimum metrics:

- feeds fetched;
- URLs discovered;
- URLs new;
- URLs duplicate;
- URLs rejected;
- feed errors;
- discovery duration.

Dependencies:

- Depends on: Task 2.3.

### Step 2 Definition of Done

- VnExpress RSS is configured.
- URLs are discovered automatically.
- Manual URL mode remains only for debugging.
- sources, source_feeds, crawl_runs, and crawl_items exist.
- URLs are normalized and deduplicated.
- Discovery has fixture-based tests.
- Discovery counters are visible.

## 5. Step 3 — Fetch, raw documents, and article ingestion

### Goal

Complete Crawl/Data Ingestion V1 for VnExpress:

    RSS -> crawl_items -> HTTP fetch -> browser fallback
       -> raw_documents -> parser -> validation -> articles

### Current state

Selenium is the only fetcher. rawdata combines raw artifact metadata, crawl
status, errors, and run identity. Parsed article content is stored in JSON
sidecars rather than an articles table.

### Task 3.1 — HTTP fetch result contract

Files/modules:

- NEW: crawler/fetchers/base.py
- NEW: crawler/fetchers/http.py
- NEW: crawler/models/fetch_result.py
- NEW: tests/unit/test_http_fetcher.py
- CHANGE: scripts/requirements.txt
- CHANGE: airflow/Dockerfile if needed.

Database impact:

- NONE directly.

FetchResult should contain:

- status_code;
- final_url;
- content_type;
- etag;
- last_modified;
- response_time_ms;
- body;
- fetch_method.

Use a feature flag such as HTTP_FIRST. Do not remove Selenium yet.

Dependencies:

- Depends on: Step 2.
- Blocks: Task 3.2 and Task 3.5.

Tests:

- 200;
- 404;
- 429;
- 500;
- timeout;
- redirect;
- unsupported content type.

### Task 3.2 — Browser fallback

Files/modules:

- NEW: crawler/fetchers/browser.py
- CHANGE: scripts/crawl_to_db.py
- CHANGE: airflow/dags/crawl_vnexpress.py
- DEPRECATE: direct Selenium implementation in the orchestration module.

Database impact:

- NONE directly.

Implementation:

    HTTP fetch
        -> usable article HTML: continue
        -> insufficient HTML: browser fallback

Keep Selenium as the fallback. Do not switch to Playwright without a concrete
runtime reason.

Dependencies:

- Depends on: Task 3.1.
- Blocks: Task 3.5.

Tests:

- HTTP success avoids browser startup.
- Insufficient HTML invokes browser fallback.
- Browser timeout.
- Browser blocked page.
- Final URL is preserved.

### Task 3.3 — raw_documents and articles schema

Files/modules:

- NEW: database/migrations/004_raw_documents_articles.sql
- NEW: crawler/repositories/raw_documents.py
- NEW: crawler/repositories/articles.py
- CHANGE: database/init/
- CHANGE: scripts/crawl_to_db.py

Database impact:

Create raw_documents:

- id
- source_id
- crawl_item_id
- url
- final_url
- content_type
- http_status
- raw_object_key
- raw_payload_type
- raw_content_hash
- raw_size_bytes
- fetched_at
- created_at

Create articles:

- id
- source_id
- raw_document_id
- canonical_url
- title
- lead
- content
- author
- published_at
- language
- section
- thumbnail_url
- content_hash
- extraction_version
- created_at
- updated_at

Migration strategy:

- Keep rawdata.
- Backfill successful rawdata rows into raw_documents.
- Backfill metadata JSON into articles only when mapping is reliable.
- Inventory unreferenced legacy artifacts; do not guess their database relation.
- Switch new writes only after verification.
- Keep rawdata as a legacy/read-only compatibility source for one transition
  period.

Dependencies:

- Depends on Task 2.1 and the Step 1 metadata contract.
- Can run in parallel with Task 3.1.
- Blocks Task 3.5.

Tests:

- Empty database migration.
- Existing database migration.
- Backfill row/hash counts.
- Raw document references.
- Article-to-raw-document references.

### Task 3.4 — Parser and validation contract

Files/modules:

- NEW: crawler/parsers/base.py
- NEW: crawler/parsers/vnexpress.py
- NEW: crawler/services/validation.py
- NEW: tests/unit/test_vnexpress_parser.py
- NEW: tests/unit/test_article_validation.py
- CHANGE: scripts/crawl_to_db.py

Database impact:

- Writes parsed/validation state to the relevant repositories.

Extraction order:

    JSON-LD
        -> OpenGraph/meta
        -> source-specific selectors
        -> generic fallback

Minimum validation:

- title exists;
- content exists;
- content length is reasonable;
- paragraph count is reasonable;
- page is not a homepage;
- page is not a captcha/blocked page;
- page is not a 404 template;
- page is not a login wall.

Do not use one SUCCESS status for fetch, parse, validation, and storage.

Dependencies:

- Depends on: Step 1 fixtures.
- Blocks Task 3.5.

Tests:

- title;
- lead/content;
- missing author;
- missing published time;
- JSON-LD;
- OpenGraph;
- blocked page;
- homepage redirect;
- empty content;
- short content.

### Task 3.5 — Per-item ingestion orchestration

Files/modules:

- CHANGE: airflow/dags/crawl_vnexpress.py
- NEW: crawler/services/ingestion.py
- NEW: crawler/repositories/crawl_items.py
- NEW: tests/integration/test_ingestion_pipeline.py

Database impact:

- Writes crawl_items, raw_documents, and articles.

Implementation:

Each crawl item is independent:

    crawl_item
        -> fetch
        -> raw storage
        -> raw_document
        -> parse
        -> validate
        -> article

Airflow Dynamic Task Mapping is sufficient at this scale. Celery is not needed
yet.

Dependencies:

- Depends on Tasks 3.1, 3.2, 3.3, and 3.4.
- Blocks Step 4.

Tests:

- Full fixture pipeline.
- One item timeout and another item success.
- Retry failed item.
- Retry does not duplicate raw documents.
- Article points to the correct raw document.
- Database transaction failure.

### Step 3 Definition of Done

- HTTP-first fetcher exists.
- Selenium/browser fallback exists.
- raw_documents exists.
- articles exists.
- Validation exists.
- Processing is independent per crawl item.
- Actual HTTP status is stored.
- Raw metadata and crawl state are separate.
- Existing rawdata is preserved.
- VnExpress RSS-to-article pipeline works end to end.

## 6. Step 4 — Reliability and multi-source

### Goal

Make the core pipeline independent of VnExpress and prove that a new source can
be added without copying the entire crawler.

### Task 4.1 — Parser interface and registry

Files/modules:

- NEW: crawler/parsers/base.py
- NEW: crawler/parsers/registry.py
- NEW: crawler/parsers/generic.py
- NEW: crawler/parsers/dantri.py
- NEW: tests/fixtures/dantri/
- NEW: tests/unit/test_parser_registry.py
- CHANGE: crawler/parsers/vnexpress.py

Database impact:

- NONE, except optional parser/extraction version fields.

Implementation:

Common interface:

    can_parse(source, url, html)
    parse(html) -> ParsedArticle

Roll out one additional Vietnamese source before adding an international
source.

Dependencies:

- Depends on Task 3.4.
- Blocks Task 4.4.

### Task 4.2 — Fetch attempts and retry policy

Files/modules:

- NEW: database/migrations/005_fetch_attempts.sql
- NEW: crawler/repositories/fetch_attempts.py
- NEW: crawler/services/retry_policy.py
- NEW: tests/unit/test_retry_policy.py

Database impact:

Create fetch_attempts:

- id
- crawl_item_id
- attempt_no
- fetch_method
- status_code
- final_url
- content_type
- response_time_ms
- error_type
- error_message
- started_at
- finished_at

Retryable:

- timeout;
- connection reset;
- 429;
- 500;
- 502;
- 503;
- 504.

Permanent or limited retry:

- invalid URL;
- 400;
- 404;
- 410;
- unsupported content;
- robots denied.

Dependencies:

- Depends on Task 3.5.
- Blocks Task 4.4.

### Task 4.3 — Rate limit and source policy

Files/modules:

- NEW: crawler/services/rate_limiter.py
- NEW: crawler/services/robots_policy.py
- NEW: tests/unit/test_rate_limiter.py
- CHANGE: source configuration
- CHANGE: Airflow configuration
- CHANGE: docs/airflow.md

Database impact:

Store per-source policy in sources.config_json initially:

- requests_per_second;
- min_delay_seconds;
- robots_policy;
- user_agent.

Implementation:

Rate limiting must be per source/domain. Do not use one global sleep value.
Respect robots.txt, terms of service, and source access rules.

Dependencies:

- Depends on Task 2.1 and Task 4.1.
- Can run in parallel with Task 4.2.
- Blocks Task 4.4.

### Task 4.4 — Reliability metrics and second-source rollout

Files/modules:

- CHANGE: Airflow DAGs
- CHANGE: backend/app.py only if inspection endpoints are needed
- NEW: crawler/observability/metrics.py
- NEW: tests/integration/test_multi_source_pipeline.py

Database impact:

- Add aggregate counters to crawl_runs if needed.
- Prometheus is not required yet.

Metrics:

- URLs discovered;
- fetch success rate;
- HTTP status distribution;
- timeout count;
- 429/403 count;
- parse success rate;
- validation failure rate;
- duplicate count;
- average latency.

Dependencies:

- Depends on Tasks 4.1, 4.2, and 4.3.
- Blocks Step 5.

### Step 4 Definition of Done

- Parser registry exists.
- At least two sources use the same core flow.
- Retry classification exists.
- fetch_attempts history exists.
- Rate limit is per source.
- Robots/policy decisions are visible.
- Metrics can be grouped by source.

## 7. Step 5 — Productionize data collection

### Goal

Prepare for larger URL/source volume without adding distributed infrastructure
before the current system has a measurable bottleneck.

### Task 5.1 — Object storage abstraction

Files/modules:

- NEW: crawler/storage/base.py
- NEW: crawler/storage/local.py
- NEW: crawler/storage/object_store.py
- NEW: tests/integration/test_object_storage.py
- CHANGE: scripts/crawl_to_db.py
- CHANGE: docker-compose.yml only if local MinIO is enabled

Database impact:

- raw_documents.raw_object_key remains the object reference.

Implementation:

Use immutable content-addressed keys:

    raw/<source>/<yyyy>/<mm>/<dd>/<content_hash>.html.gz

Migration path:

    local storage
        -> dual read/write
        -> checksum verification
        -> object storage primary
        -> local fallback during transition

Do not delete local artifacts before checksum and row-count verification.

Dependencies:

- Depends on Step 3 raw_documents.
- Blocks Task 5.3.

### Task 5.2 — Scaling decision: Airflow or queue

Files/modules:

- CHANGE: Airflow DAGs if concurrency changes
- CHANGE: docker-compose.yml only if Redis/Celery is justified
- NEW: docs/architecture/crawl-scaling.md

Database impact:

- NONE directly.

Airflow Dynamic Task Mapping remains sufficient while:

- runs contain tens to a few hundred URLs;
- runs fit the DAG timeout;
- concurrency can be bounded;
- a separate worker pool is not needed.

Consider Celery/Redis when:

- runs regularly exceed the allowed time;
- URL volume reaches hundreds or thousands per run;
- browser workers need independent horizontal scaling;
- Airflow scheduler becomes the bottleneck.

Dependencies:

- Depends on Step 4 metrics.
- Blocks Task 5.4 only if a queue is selected.

### Task 5.3 — Monitoring, retention, and operations

Files/modules:

- NEW: crawler/observability/
- NEW: docs/operations/crawler.md

Database impact:

Possible later fields:

- crawl_runs.retention_until;
- raw_documents.retention_until.

Metrics:

- URLs discovered;
- fetch success rate;
- HTTP errors;
- timeouts;
- 429/403;
- parse success;
- validation failures;
- duplicates;
- orphan artifacts;
- average latency.

Retention must cover:

- raw HTML;
- metadata;
- failed attempts;
- old crawl runs.

Dependencies:

- Depends on Tasks 5.1 and 5.2.

### Task 5.4 — Rollback and security controls

Files/modules:

- CHANGE: .env.example
- CHANGE: docker-compose.yml only when new services are added
- CHANGE: operations documentation

Database impact:

- Use expand/contract migrations.
- Do not drop rawdata during the transition.

Controls:

- HTTP-first feature flag;
- Selenium fallback;
- local storage fallback;
- source/domain allowlist;
- no secrets in repository;
- checksum verification;
- migration rollback rehearsal.

Dependencies:

- Depends on Tasks 5.1 and 5.3.

### Step 5 Definition of Done

- Storage backend has a stable interface.
- Object storage migration is verified by checksums.
- Retention policy exists.
- Orphan detection exists.
- Monitoring MVP exists.
- Airflow-to-Celery threshold is documented.
- Storage, fetcher, and database rollback paths are documented.

## 8. Database evolution plan

Do not rename or drop rawdata immediately.

Migration path:

    rawdata
        -> sources/source_feeds/crawl_runs/crawl_items
        -> raw_documents/articles
        -> backfill and verify
        -> switch writes
        -> rawdata legacy/read-only
        -> remove only in a later release

### Step 1

- Keep rawdata.
- Add compatibility and idempotency checks.
- Preflight duplicate rows.
- Do not add destructive constraints before cleanup.
- Do not delete artifacts.

### Step 2

Create:

- sources;
- source_feeds;
- crawl_runs;
- crawl_items.

Seed VnExpress and map the existing source_id=1 before adding foreign keys.

### Step 3

Create:

- raw_documents;
- articles.

Backfill only records with reliable mappings. Treat unreferenced legacy files
as an inventory problem, not as data that can be guessed into the database.

### Step 4

Create fetch_attempts and move retry/error history away from raw_documents.

### Step 5

Add retention and object-storage metadata only when those systems are enabled.

Recommended indexes and constraints:

- unique source name;
- unique source/feed URL;
- unique source/normalized URL for persistent crawl items;
- index crawl item status;
- index next attempt time;
- index raw content hash;
- index article content hash.

Do not make raw_content_hash globally unique because identical content from
different sources still needs provenance.

## 9. Codebase evolution plan

### Current files

- airflow/dags/crawl_vnexpress.py
- scripts/crawl_to_db.py
- database/init/001_create_rawdata.sql
- database/migrations/002_add_rawdata_payload_and_run.sql
- backend/app.py

### After Step 1

- tests/unit/
- tests/integration/
- tests/fixtures/

Keep the existing crawler module until the contract and tests are stable.

### After Step 2

    crawler/
    ├── discovery/
    ├── models/
    └── repositories/

### After Step 3

    crawler/
    ├── fetchers/
    ├── parsers/
    ├── storage/
    ├── repositories/
    └── services/

The backend should only add article endpoints after the articles data contract
exists. The current backend is only health/db-check.

## 10. Test strategy

### Unit tests

- URL normalization.
- Content hash.
- Metadata schema.
- Parser.
- Validation.
- RSS parsing.
- Retry classification.
- Rate limiting.

### Integration tests

- Fetch to raw storage.
- Raw storage to raw_documents.
- Parser to articles.
- Discovery to crawl_items.
- Database migration and backfill.
- Artifact reconciliation.

### Pipeline tests

    RSS fixture
        -> URL
        -> crawl_item
        -> fetch
        -> raw document
        -> article

### Regression fixtures

At minimum:

- normal VnExpress article;
- missing author;
- missing published_at;
- short article;
- no content;
- blocked/captcha page;
- homepage redirect;
- malformed RSS.

CI should not depend on live Internet access. Live 20–50 article tests should
be opt-in smoke tests.

## 11. Dependency graph

    1.1 Config guard
        -> 1.2 Metadata contract
        -> 1.3 URL/idempotency
        -> 1.4 Tests
        -> 2.1 Source schema
        -> 2.2 RSS discovery
        -> 2.3 Discovery orchestration
        -> 2.4 Discovery metrics
        -> 3.1 HTTP fetch contract
        -> 3.2 Browser fallback
        -> 3.3 Raw/article schema
        -> 3.4 Parser/validation
        -> 3.5 Ingestion V1
        -> 4.1 Parser registry
        -> 4.2 Fetch attempts/retry
        -> 4.3 Rate/policy
        -> 4.4 Multi-source metrics
        -> 5.1 Object storage
        -> 5.2 Scaling decision
        -> 5.3 Monitoring/retention
        -> 5.4 Rollback/security

Parallelizable work:

- Step 1 normalization tests and metadata tests.
- Step 2 source schema and RSS parser.
- Step 3 HTTP fetcher and database schema design.
- Step 4 parser registry and retry policy.
- Step 5 storage abstraction and retention documentation.

Sequential gates:

- Step 1 must be stable before discovery.
- Discovery must create crawl items before per-item ingestion.
- Raw/article schema and parser validation must exist before the full ingestion
  pipeline.
- VnExpress ingestion must be stable before multi-source rollout.
- Metrics must exist before deciding whether Celery is needed.

## 12. Risk and rollback plan

| Step | Risk | Level | Mitigation | Rollback |
| --- | --- | --- | --- | --- |
| Step 1 | Retry duplicates | HIGH | Stable run ID and idempotent write | Disable new constraint/write path |
| Step 1 | Parser regression | MEDIUM | Fixtures and regression tests | Keep old parser behind flag |
| Step 1 | Metadata incompatibility | HIGH | schema_version and legacy reader | Support v1/v2 reads |
| Step 2 | RSS format change | MEDIUM | Fixtures and tolerant parser | Return to manual mode |
| Step 2 | Bad discovered URLs | HIGH | Source allowlist and validation | Disable source/feed |
| Step 3 | HTTP misses JS content | MEDIUM | Browser fallback | Set HTTP_FIRST=false |
| Step 3 | Migration error | HIGH | Expand/contract and count checks | Keep rawdata unchanged |
| Step 3 | Raw/article mismatch | HIGH | Transactions and reconciliation | Reprocess from raw |
| Step 4 | Source block/429 | HIGH | Rate limit and backoff | Disable source |
| Step 4 | New parser regression | MEDIUM | Registry and fixtures | Disable parser/source |
| Step 5 | Object upload failure | HIGH | Checksum and dual-read/write | Read local storage |
| Step 5 | Queue over-engineering | MEDIUM | Measurable scaling threshold | Keep Airflow mapping |

Do not delete rawdata, old raw HTML, or old metadata until row counts,
content hashes, and object references have been reconciled.

## 13. Final Definition of Done

- [ ] VnExpress RSS is configured.
- [ ] Normal operation does not require manual URL input.
- [ ] Manual URL mode remains available for debugging.
- [ ] URLs are normalized.
- [ ] Duplicate URLs do not create duplicate crawl items.
- [ ] sources exists.
- [ ] source_feeds exists.
- [ ] crawl_runs exists.
- [ ] crawl_items exists.
- [ ] HTTP fetcher exists.
- [ ] Browser fallback exists.
- [ ] Actual HTTP status is stored.
- [ ] Raw artifacts are immutable.
- [ ] raw_documents exists.
- [ ] Source-specific parser registry exists.
- [ ] Validation exists.
- [ ] articles exists in PostgreSQL.
- [ ] Raw content hash and article content hash are distinct.
- [ ] One URL failure does not fail unrelated URLs.
- [ ] Retry does not create duplicates.
- [ ] Retry classification exists.
- [ ] Source-specific rate limiting exists.
- [ ] Offline parser fixtures exist.
- [ ] Integration tests exist.
- [ ] Discovery/fetch/parse metrics exist.
- [ ] Orphan artifact detection exists.
- [ ] There is a migration path from rawdata.
- [ ] Existing data is preserved.
- [ ] Rollback paths are documented.

## 14. Recommended implementation order

1. Task 1.1 — Configuration guard and manual mode.
2. Task 1.2 — Metadata schema v2.
3. Task 1.3 — Stable crawl run ID and idempotency.
4. Task 1.4 — Parser, storage, and regression tests.
5. Task 2.1 — Source, feed, run, and item schema.
6. Task 2.2 — VnExpress RSS parser.
7. Task 2.3 — Discovery orchestration.
8. Task 2.4 — Discovery metrics.
9. Task 3.1 — HTTP fetch result contract.
10. Task 3.2 — Browser fallback.
11. Task 3.3 — raw_documents and articles schema.
12. Task 3.4 — Parser and validation contract.
13. Task 3.5 — Per-item ingestion pipeline.
14. Task 4.1 — Parser registry.
15. Task 4.2 — Fetch attempts and retry policy.
16. Task 4.3 — Rate limit and robots/source policy.
17. Task 4.4 — Second source and reliability metrics.
18. Task 5.1 — Object storage abstraction.
19. Task 5.2 — Airflow scaling decision.
20. Task 5.3 — Monitoring and retention.
21. Task 5.4 — Rollback and security controls.

## 15. First implementation batch

The first implementation batch should remain within Step 1. It should not add
RSS or new database tables yet.

Expected files to change:

- airflow/dags/crawl_vnexpress.py
- scripts/crawl_to_db.py
- scripts/crawl_contract.py
- scripts/crawl_config.py
- .env.example
- docs/airflow.md
- docs/step_01_news_article_crawler.md

Expected new files:

- tests/unit/test_dag_config.py
- tests/unit/test_url_normalization.py
- tests/unit/test_metadata_schema.py
- tests/unit/test_vnexpress_parser.py
- tests/integration/test_retry_idempotency.py
- tests/integration/test_local_storage.py
- tests/unit/test_reconcile_crawl_artifacts.py
- tests/fixtures/vnexpress/normal.html
- tests/fixtures/vnexpress/missing_author.html
- tests/fixtures/vnexpress/no_content.html

Also implemented:

- `scripts/reconcile_crawl_artifacts.py` — read-only orphan/hash/legacy scan.
- `tests/fixtures/metadata/v2_success.json` and `v2_failed.json`.
- `tests/fixtures/vnexpress/blocked.html`.

Database:

- Do not create new tables in the first batch.
- Preflight current duplicates.
- Design, but do not immediately enforce, a uniqueness constraint.
- Do not delete rawdata or existing artifacts.

Required tests:

- Unit tests for normalization and parser.
- Metadata schema tests.
- Empty HTML and missing content.
- Invalid URL and timeout.
- One failed URL does not stop the next URL.
- Retry does not create duplicate records.
- Artifact/database reconciliation.

Acceptance criteria:

- [x] Empty CRAWL_URLS is handled explicitly.
- [x] New metadata uses one schema and schema_version.
- [x] Retry does not create duplicate records or raw artifacts.
- [x] One failed URL does not stop the next URL.
- [x] Parser runs offline using fixtures.
- [x] Artifact and database references can be reconciled.
- [x] No existing code, database row, or artifact is deleted.
