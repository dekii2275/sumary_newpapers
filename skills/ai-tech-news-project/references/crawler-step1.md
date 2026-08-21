# Step 1 crawler contract

## Goal

Build a single-article crawler that receives a URL, loads the rendered page with Selenium (or an explicitly approved compatible fetcher), parses it with BeautifulSoup, and stores reproducible raw data for later processing.

## Required boundaries

Keep these components separate:

```text
Fetcher -> rendered HTML + final URL/status
Parser  -> article fields
Model   -> stable raw article schema
Storage -> raw HTML + metadata JSON (local MVP)
```

Do not put fetching, parsing, database writes, deduplication, or AI calls in one crawler class.

## Stable raw article shape

The implementation should preserve these fields, with `null`/`None` allowed where the source does not provide a value:

```json
{
  "source": "vnexpress",
  "url": "https://example.com/article",
  "final_url": "https://example.com/article",
  "title": "Article title",
  "author": null,
  "published_at": null,
  "content": "Article body",
  "thumbnail_url": null,
  "raw_html_path": "data/raw/...html.gz",
  "http_status": 200,
  "crawl_status": "SUCCESS",
  "fetched_at": "2026-08-21T20:00:00+07:00"
}
```

Recommended failure statuses are `TIMEOUT`, `PAGE_NOT_FOUND`, `BLOCKED`, `EMPTY_HTML`, `PARSE_FAILED`, `CONTENT_NOT_FOUND`, and `UNKNOWN_ERROR`. A batch should record a failed item and continue.

## Parsing guidance

- Start with semantic metadata and source-specific selectors: `h1`, `time[datetime]`, `meta[property="og:image"]`, and the source's article-body container.
- Strip empty paragraphs and incidental whitespace, but do not claim that Step 1 has produced fully cleaned canonical content.
- Keep selectors/configuration isolated per source so a future source does not require rewriting the fetcher.
- Preserve `final_url` after redirects and record the fetch timestamp with timezone information.

## Storage and operational behavior

- Store raw HTML under a deterministic, date-partitioned path such as `data/raw/<source>/YYYY/MM/DD/<hash>.html.gz`.
- Store metadata JSON separately under `data/metadata/<source>/...json`.
- Normalize tracking parameters (`utm_source`, `utm_medium`, `utm_campaign`, `fbclid`, `gclid`) before URL hashing.
- Use one browser session for sequential MVP crawling; do not create hundreds of browser instances.
- Add explicit waits, a bounded timeout, honest User-Agent identification, structured logs, and a modest per-source delay.
- Prefer RSS or a documented API over browser automation when the source provides one.

## Minimum verification

Test at least:

1. rendered HTML is non-empty;
2. title and content extraction work for a fixture;
3. optional author/time/image fields can be missing without failure;
4. raw HTML and metadata files are written as UTF-8;
5. invalid URLs/timeouts produce a non-success status rather than crashing;
6. one failed URL does not stop a batch.

For a representative MVP sample, aim for 20-50 articles across short/long, AI/startup/research, and image-heavy articles. Treat success-rate targets as measurements, not hardcoded parser rules.

