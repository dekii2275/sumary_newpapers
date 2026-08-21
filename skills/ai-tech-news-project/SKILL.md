---
name: ai-tech-news-project
description: Develop and extend this AI technology news intelligence platform, preserving its staged architecture and current crawler MVP scope. Use for repository changes involving news collection, article data, backend/frontend scaffolding, NLP/RAG, content generation, or short-video automation.
metadata:
  short-description: Project-aware engineering for AI Tech News
---

# AI Tech News Project

Use this skill when working inside the AI Tech News repository. Treat the repository as an early-stage scaffold: the immediate implementation target is Step 1, a single-article crawler, while later AI, search, content, and video capabilities must be introduced incrementally.

## First read

- Read `README.md` for the product vision, stack, services, and roadmap.
- Read `docs/step_01_news_article_crawler.md` for the current implementation contract.
- Read [references/project-context.md](references/project-context.md) for the condensed product and architecture context.
- For crawler work, also read [references/crawler-step1.md](references/crawler-step1.md).
- For later intelligence, RAG, content, or video work, read [references/future-pipelines.md](references/future-pipelines.md) only when that mode is in scope.

## Mode selection

Choose the smallest mode that satisfies the request:

1. **Crawler MVP**: Selenium/Playwright fetch, BeautifulSoup parsing, raw HTML, metadata, local storage, logging, and error handling.
2. **Backend/data**: FastAPI endpoints, PostgreSQL models, migrations, background jobs, object storage, or service boundaries.
3. **Frontend**: Next.js/TypeScript news pages, article detail, TL;DR, Ask AI, or admin views.
4. **Intelligence and media**: NLP/LLM extraction, summarization, hybrid RAG, content angles, TTS, subtitles, and short-video rendering.

Do not implement a later mode merely because it is described in the roadmap. Confirm that the requested change needs it.

## Engineering rules

- Preserve the separation between fetching, parsing, domain models, and storage. A fetcher returns rendered HTML and response metadata; a parser turns HTML into article fields; storage persists raw HTML and metadata.
- Keep one stable `RawArticle`-shaped output even when optional fields are missing. Do not silently drop failed URLs.
- Prefer official RSS/API interfaces when available. For browser crawling, respect robots.txt, terms, rate limits, and the source's access rules; identify the crawler honestly.
- Keep raw HTML for reproducibility. Do not overwrite a prior crawl without an explicit retention decision.
- Normalize URLs before deduplication, remove known tracking parameters, and use deterministic IDs or hashes for files and idempotency.
- Treat selectors as source-specific and changeable. Do not pretend that one CSS selector works for every site; isolate source-specific parsing logic.
- Use environment variables for secrets and deployment settings. Never commit API keys, credentials, or production endpoints.
- Keep the first implementation small and testable. Add a dependency only when the feature needs it and update the relevant requirements/package manifest.
- Add tests for success, partial/missing fields, invalid URLs, timeouts, empty content, and a failed item that does not stop a batch.
- Before changing architecture, inspect the current files and preserve unrelated user changes. Verify with focused tests or build checks appropriate to the changed layer.

## Scope guard for Step 1

Step 1 ends at a reliable raw article object plus raw HTML and metadata. It does not include deduplication beyond basic URL normalization, classification, entity extraction, summarization, embeddings, vector search, RAG, content generation, or video rendering. Those belong to later stages unless the user explicitly expands scope.

## Delivery checklist

Before handing off a change, report:

- what changed and which mode it belongs to;
- the data contract or API surface affected;
- tests/build checks run and their result;
- any source-specific assumptions, missing dependencies, or follow-up work.

