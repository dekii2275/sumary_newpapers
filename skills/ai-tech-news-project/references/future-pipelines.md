# Later pipeline guidance

Read this reference only when the request is explicitly beyond crawler Step 1.

## Data processing and canonicalization

Clean HTML/boilerplate, detect language, normalize text, compare normalized URLs and content, and group near-duplicates into a canonical article. Keep raw crawl records linked to the canonical record so provenance is not lost.

## News understanding

Enrich normalized articles with topic/category classification, named entities, summaries, key points, impact analysis, importance scoring, topic/event links, and embeddings at article, summary, and chunk levels. Prefer typed schemas and validation for LLM output; preserve source spans or citations where feasible.

## Retrieval and chat

- Article Chat uses the current article plus a small related context.
- Global News Chat rewrites intent and time ranges, combines lexical/BM25 and vector search, reranks results, and generates answers with source citations.
- Keep retrieval and generation observable. Do not let the LLM invent citations or facts unsupported by retrieved records.

## Content and video

The content agent selects an angle such as Breaking News, Why It Matters, 3 Things You Should Know, Developer Perspective, or Comparison, then generates platform-specific formats. The short-video pipeline separates hook, context, key information, practical meaning, conclusion, and CTA before producing a visual plan, voice script, captions/hashtags, TTS, assets, and final rendering.

Keep content generation traceable to canonical articles. Media files belong in object storage, while metadata and render jobs belong in the relational/job system.

