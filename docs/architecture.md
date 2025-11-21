# Intelligent Campus Notice Platform - Backend Architecture

## 1) Current Scope
- FastAPI app serving `/api/*` endpoints for feed, search, chat, likes, reminders, and a minimal recommendation stub.
- MongoDB (Beanie ODM) stores posts, users, interactions, reminders. Qdrant stores embeddings; collection is auto-created on first use.
- LLM calls (summary/classification/embedding/chat) are optional. When keys are missing the app falls back to deterministic summaries/embeddings so flows still work.
- Dummy/local notice sources plus sample HTML crawling power ingest in development; APScheduler can run the ingest loop when enabled.

## 2) Runtime Architecture
```
NoticeSource (dummy | local | catalog | HTML)
          │
          ▼
    IngestPipeline ──► Normalize/LLM ► Mongo `posts`
          │                           │
          │                           └─► Vector upsert to Qdrant (`notice_vectors`)
          │
          ▼
FastAPI routers (/api) ─► Services ─► Mongo queries + Qdrant search
                                    └─► LLM calls (optional)
```
- App lifecycle (`app/main.py`) wires CORS, includes `/api` router, and starts/stops Mongo and APScheduler.
- Scheduler (`app/core/scheduler.py`) runs the ingest pipeline on an interval when `SCHEDULER_ENABLED=true`.

## 3) Modules & Responsibilities
- **API Layer** (`app/api/*`): request validation and simple orchestration.
- **FeedService**: fetches posts sorted by `posted_at`, filters by `category`, excludes seed/dummy sources, formats items.
- **SearchService**: keyword search via Mongo regex; semantic search via Qdrant using LLM embeddings, with automatic fallback to keyword.
- **RecommendationService**: like-based semantic recommendations from recent liked posts; falls back to baseline feed. Profile route is stubbed (see gaps).
- **ChatService**: RAG-style answer generation. Retrieves contexts from Qdrant + keyword search, applies guardrails, verifies LLM answers, or falls back to templated text.
- **ReminderService / InteractionService**: CRUD helpers for reminders and likes; keeps user like cache and post like counts in sync.
- **LLMService & Vector Store**: LLM HTTP client with fallbacks; Qdrant collection bootstrap, vector upsert/search helpers.
- **Ingest** (`app/ingest/*`): source adapters, normalization/tagging/hash, pipeline that dedupes notices, enriches with LLM summary/category, writes Mongo + Qdrant.

## 4) Data Model (Mongo & Qdrant)
- `posts`: `title`, `url`, `posted_at`, `deadline_at`, `body`, `summary`, `tags[]`, `college`, `department`, `audience_grade[]`, `category`, `source`, `hash` (unique), `likes`, timestamps.
- `users`: `email` (unique), `college`, `department`, `grade`, `interests[]`, `liked_post_ids[]`, `preference_vector_id`, `created_at`.
- `interactions`: `user_id`, `post_id`, `type` (`view|like|save`), `ts`, optional `metadata`.
- `reminders`: `user_id`, `post_id`, `notify_at`, `channel` (`email|kakao`), `status`, `created_at`.
- Qdrant (`notice_vectors`): single cosine vector of size `QDRANT_VECTOR_SIZE` with payload `{post_id, department, audience_grade, posted_at, deadline_at, tags, category, source}`.

## 5) API Surface (prefix `/api`)
| Method | Path | Purpose | Notes |
| --- | --- | --- | --- |
| GET | `/` | Service info | name/environment message |
| GET | `/healthz` | Health | timezone + status |
| GET | `/feed` | Baseline feed | `category?`, excludes dummy sources, sorted by `posted_at`; returns `{id,title,tags,category,source[],posted_at,deadline}` |
| GET | `/feed/reco-user` | Profile stub | Currently calls FeedService with unsupported args (see gaps) |
| GET | `/feed/reco-likes` | Like-based reco | `user_id`, `limit`; semantic from liked posts → fallback feed |
| GET | `/posts/{id}` | Post detail | Returns raw Post document |
| GET | `/search` | Keyword/semantic search | `q`, `mode=keyword|semantic`, `department?`, `grade?`; semantic falls back to keyword on failure |
| POST | `/likes` | Like a post | `{user_id, post_id}` updates likes cache/count |
| DELETE | `/likes/{user_id}/{post_id}` | Remove like | idempotent delete |
| POST | `/reminders` | Create reminder | `{user_id, post_id, notify_at, channel}` |
| GET | `/reminders` | List reminders | `user_id`, pagination |
| POST | `/chat` | RAG QA | `{question, user_id?, department?, grade?}` with guardrails and verification |

## 6) Ingest & Background Jobs
- Sources: dummy notice, local dummy dataset, sample scholarship/internship adapters, optional HTML crawler, and catalog-driven adapters.
- Pipeline: fetch → normalize/tag/hash → skip duplicates → LLM summary + category → embed → write Mongo → upsert vector to Qdrant.
- Scheduler: optional APScheduler interval job runs the ingest pipeline; otherwise use `scripts/run_ingest.py`.

## 7) Configuration & Ops Highlights
- Key envs: Mongo/Qdrant connection, `QDRANT_VECTOR_SIZE`, `LLM_*` keys/base URLs, `SCHEDULER_ENABLED`, `CRAWLER_SAMPLE_HTML`, `BOARD_CATALOG_*`.
- CORS allows `http://localhost:5173` and `http://localhost:3000`.
- Vector collection is bootstrapped on first embed/search call; falls back to pseudo vectors when embedding keys are missing.

## 8) Known Gaps / Alignment Items
- `RecommendationService.profile_recommendations` still passes `department/grade` into `FeedService.get_feed`, which only accepts `category`; the `/feed/reco-user` route will error until the signature is aligned.
- Feed scoring/advanced ranking, auth, rate limiting, and multi-channel notification delivery are not implemented yet (responses are simple lists with pagination meta).
