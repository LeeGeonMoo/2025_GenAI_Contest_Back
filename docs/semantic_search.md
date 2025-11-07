# Semantic Search & LLM Integration (Pre-Crawler)

This document outlines the features implemented **before** wiring real crawlers.
It explains how LLM-powered summarisation/embeddings, Qdrant vectors, and
semantic endpoints are configured.

## 1. Configuration
Add the following keys to `.env` (see `.env.example` for defaults):

```
LLM_API_BASE=https://api.your-llm-provider.com
LLM_API_KEY=sk-...
LLM_SUMMARY_MODEL=gpt-3.5-turbo
LLM_EMBEDDING_MODEL=text-embedding-3-small
QDRANT_COLLECTION_NOTICES=notice_vectors
QDRANT_VECTOR_SIZE=768
SCHEDULER_ENABLED=true
```

- If `LLM_API_BASE` or `LLM_API_KEY` is missing, `LLMService` automatically falls
  back to heuristic summaries and deterministic pseudo embeddings so the system
  remains testable.
- Qdrant collection bootstrapping happens on first use via
  `app/services/vector_store.py`.

## 2. LLM Service
- `app/clients/llm.py`: generic HTTP client for chat-completion and embedding
  endpoints (OpenAI-compatible schema). It exposes `generate_summary` and
  `embed_text`.
- `app/services/llm_service.py`: wraps the client, providing async methods
  `summarize`/`embed` with logging and graceful fallbacks.
- Tests in `tests/test_llm_service.py` ensure fallback behaviour works when the
  real API is disabled.

## 3. Ingest Pipeline
- `app/ingest/pipeline.py` now calls `LLMService` for summaries/embeddings and
  mirrors vectors into Qdrant via `vector_store.upsert_notice_vector`.
- `scripts/run_ingest.py` reports `inserted/skipped/vectorized` counts so you can
  verify both Mongo and Qdrant are updated.
- `CRAWLER_SAMPLE_HTML` can point to either `docs/sample_pages/scholarship_board.html`
  or a live board URL, enabling the HTML crawler to ingest real pages even
  before full crawler coverage exists.

## 4. Semantic Search
- `/search` accepts `mode=keyword|semantic`. When `semantic`, the query is
  embedded, Qdrant returns similar notices, and the API returns ordered results
  with `semantic_score`. If any step fails, the system gracefully falls back to
  the keyword search.

## 5. Recommendations
- `/feed/reco-likes` attempts to build a semantic query from the user's liked
  posts (when available) and reuses the Qdrant search results. When no likes or
  embeddings exist, it falls back to the baseline feed with metadata explaining
  the mode.

## 6. Scheduler
- `app/core/scheduler.py` hooks APScheduler into the FastAPI lifecycle. When
  enabled via `.env`, it periodically runs the ingest pipeline with dummy
  sources, ensuring the semantic components stay warm even before real crawlers
  are introduced.

## 7. Verification Workflow
1. `docker compose up --build`
2. `docker compose exec api python scripts/run_ingest.py`
3. (Optional) `docker compose exec api pytest`
4. Hit:
   - `GET /feed` (check `score`/`rank_reason`)
   - `GET /feed/reco-likes?limit=5`
   - `GET /search?q=장학&mode=semantic`

This completes the “pre-crawler” feature set: LLM hooks, semantic search,
recommendation scaffolding, and scheduled ingest ready for real data sources.
