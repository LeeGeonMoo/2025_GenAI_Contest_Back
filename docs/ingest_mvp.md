# Ingest MVP Usage

## Overview
The ingest pipeline uses a dummy notice source to simulate crawling, normalizes
the documents, generates summaries/embeddings through the LLM service (or a
deterministic fallback), writes posts into MongoDB, and mirrors vectors into
Qdrant. This exercises the end-to-end flow before attaching real boards.

## Components
- `app/ingest/base.py`: shared dataclasses (`RawNotice`, `NormalizedNotice`) and
  the `NoticeSource` protocol.
- `app/ingest/sources/dummy.py`: provides one hard-coded notice for testing.
- `app/ingest/sources/scholarship.py`, `.../internship.py`: simulate structured crawler outputs.
- `app/ingest/sources/snu_scholarship.py`: HTML crawler that parses `CRAWLER_SAMPLE_HTML`.
- `app/ingest/normalizer.py`: handles heuristic tagging/hashing before LLM enrichment.
- `app/ingest/pipeline.py`: orchestrates fetching, deduping, summary/embedding generation, and persistence.
- `scripts/run_ingest.py`: convenience script to trigger the pipeline inside the API container.
- `app/services/llm_service.py`: wraps the LLM API with graceful fallbacks.
- `app/services/vector_store.py`: manages Qdrant collection creation and upserts.

## Running the Pipeline
1. Make sure the docker stack is up:
   ```bash
   docker compose up --build
   ```
2. (Optional) configure `.env` with your LLM/Qdrant settings:
   ```
   LLM_API_BASE=https://api.your-llm-provider.com
   LLM_API_KEY=sk-...
   ```
   Without these values the fallback summariser/embedding generator is used.
3. (Optional) point `CRAWLER_SAMPLE_HTML` to a file/URL:
   ```
   CRAWLER_SAMPLE_HTML=file://path/to/local.html
   ```
   or a live board endpoint. If unset, the HTML crawler is skipped.
4. Execute the ingest script inside the API service:
   ```bash
   docker compose exec api python scripts/run_ingest.py
   ```
5. You should see output similar to:
   ```
   Ingest completed: {'inserted': 1, 'skipped': 0, 'vectorized': 1}
   ```
6. Hit `http://localhost:8000/feed` or `/search?q=장학&mode=semantic` to confirm data is accessible and vectors searchable.

## Next Steps
- Replace `DummyNoticeSource` with real crawler implementations per board.
- Swap dummy source with real crawlers and expand APScheduler jobs for ingest/reminders.
- Connect the LLM service to production-grade summary/embedding models for higher-quality vectors.
