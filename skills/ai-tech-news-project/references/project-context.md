# Project context

## Product

AI Tech News is a platform that collects AI and technology news from journalism sites, RSS/News APIs, social platforms, and technical or academic sources. It turns raw articles into structured knowledge for two audiences:

- readers who need current news, summaries, semantic search, and grounded Q&A;
- creators who need platform-specific posts, newsletters, scripts, and short videos.

The product flow is:

```text
sources -> collection/normalization -> cleaning/deduplication
        -> news understanding -> knowledge base
        -> website/news chat and content/video pipelines
```

## Current repository state

The repository is an early scaffold with:

- `backend/app.py`: FastAPI root, health, and PostgreSQL connectivity checks;
- `backend/requirements.txt`: FastAPI, psycopg, and uvicorn;
- `frontend/`: minimal Next.js/TypeScript page and layout;
- `docker-compose.yml`: PostgreSQL, backend, and frontend services;
- `docs/step_01_news_article_crawler.md`: detailed current crawler specification.

The local ports documented by the repository are frontend `13000`, backend `18080`, and PostgreSQL `15432`. Keep these defaults unless the user asks to change them.

## Target architecture

The planned stack is Next.js/TypeScript, Tailwind/shadcn UI, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Qdrant or pgvector, Redis/Celery, LangGraph, Selenium or Playwright plus BeautifulSoup/Trafilatura, an LLM provider, object storage, and FFmpeg/Remotion/MoviePy for video. These are target choices, not permission to add every dependency at once.

## Product invariants

- One raw input should serve both reader and creator workflows.
- Source provenance must remain available for article pages and future RAG citations.
- Raw documents, normalized articles, AI enrichments, and media artifacts have different lifecycles; do not collapse them into one opaque record.
- Article Chat is narrow and current-article focused; Global News Chat is a broader retrieval workflow with query rewriting, hybrid search, reranking, and citations.
- The project is staged. Reliable collection comes before AI enrichment and retrieval.

