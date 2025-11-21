# Semantic Search & LLM Integration (current)

This document reflects the code in `app/services/search_service.py`,
`app/services/chat_service.py`, and the ingest pipeline. It describes how
semantic search works today and how it falls back when LLM/Qdrant are missing.

## 1. Configuration
Add the following keys to `.env` (see `.env.example` for defaults):

```
LLM_SUMMARY_BASE=
LLM_SUMMARY_KEY=
LLM_SUMMARY_MODEL=gpt-3.5-turbo
LLM_EMBEDDING_BASE=
LLM_EMBEDDING_KEY=
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_CHAT_BASE=
LLM_CHAT_KEY=
QDRANT_COLLECTION_NOTICES=notice_vectors
QDRANT_VECTOR_SIZE=768
SCHEDULER_ENABLED=true
```

- If the summary/chat/embedding base URL or key is missing, `LLMService` automatically falls
  back to heuristic summaries and deterministic pseudo embeddings so the system
  remains testable.
- Qdrant collection bootstrapping happens on first use via
  `app/services/vector_store.py`.

## 2. LLM Service
- `app/clients/llm.py`: OpenAI-compatible HTTP client for chat/summary/embedding.
- `app/services/llm_service.py`: wraps the client, providing async `summarize`,
  `embed`, `classify_category` with logging and graceful fallbacks when the
  external LLM is unavailable.
- Tests in `tests/test_llm_service.py` ensure fallback behaviour works when the
  real API is disabled.

## 3. Ingest + Vectors
- `app/ingest/pipeline.py` calls `LLMService` for summary/category/embedding,
  dedupes by hash, writes `Post` to Mongo, and mirrors the embedding into Qdrant
  with payload metadata.
- `scripts/run_ingest.py` reports `inserted/skipped/vectorized` counts so you can
  verify both Mongo and Qdrant are updated.
- `CRAWLER_SAMPLE_HTML` enables the HTML crawler to ingest real pages before
  full coverage exists; otherwise dummy/local sources are used.

## 4. `/api/search` behaviour
- Query params: `q` (required), `mode=keyword|semantic`, optional
  `department`, `grade`, pagination.
- **Semantic mode**:
  1) Embed `q` via `LLMService.embed`. When no key is set a deterministic pseudo
     embedding is produced.
  2) Search Qdrant (`vector_store.search_similar`). Hits contain scores and
     `post_id`.
  3) Fetch matching posts from Mongo; attach `semantic_score` to each item.
  4) `meta.total` reflects the number of posts matching the department/grade
     filters (query string is not applied to this count).
  5) If any step fails or returns no hits, the service falls back to keyword mode.
- **Keyword mode**:
  - Builds a case-insensitive regex over `title|summary|body`, applies optional
    department/grade filters, paginates, and returns raw post dicts with
    `meta.total/page/page_size`.

## 5. Recommendations
- `RecommendationService._semantic_from_likes` concatenates recent liked post
  summaries/bodies, embeds the text, searches Qdrant, filters out already liked
  IDs, and returns posts with `semantic_score`.
- When embeddings/likes are missing it falls back to the baseline feed and
  annotates `meta.mode = "likes-fallback"`.

## 6. Scheduler
- `app/core/scheduler.py` hooks APScheduler into the FastAPI lifecycle. When
  enabled via `.env`, it periodically runs the ingest pipeline (dummy+sample
  sources), keeping vectors/Mongo populated for semantic search.

## 7. Verification Workflow
1. `docker compose up --build`
2. `docker compose exec api python scripts/run_ingest.py`
3. (Optional) `docker compose exec api pytest`
4. Hit:
   - `GET /api/feed`
   - `GET /api/feed/reco-likes?limit=5&user_id=<user>`
   - `GET /api/search?q=장학&mode=semantic`

Semantic search should return items with `semantic_score` when Qdrant is
populated; otherwise it will fall back to the keyword response shape.
