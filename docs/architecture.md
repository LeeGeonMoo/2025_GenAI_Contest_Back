# Intelligent Campus Notice Platform - Backend Architecture

## 1) Current Scope
- FastAPI app serving `/api/*` endpoints for feed, search, chat, likes, reminders, and user profile.
- MongoDB (Beanie) + Qdrant; collection bootstraps on first use.
- LLM calls are optional; deterministic summary/embedding fallbacks keep flows working when keys are missing.
- Dummy/local notice sources + sample HTML crawling power ingest in dev; APScheduler can run the ingest loop when enabled.

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
FastAPI (/api) ─► Services ─► Mongo queries + Qdrant search
                             └─► Optional LLM calls
```
- `app/main.py`: CORS, `/api` router, Mongo lifecycle hooks, APScheduler startup/shutdown.
- `app/core/scheduler.py`: runs ingest pipeline on interval when `SCHEDULER_ENABLED=true`.

## 3) Modules
- **API** (`app/api/*`): validation + routing.
- **FeedService**: baseline feed by `posted_at`, `category` filter, dummy/seed source exclusion, response formatting.
- **SearchService**: Mongo regex keyword search; LLM embedding + Qdrant semantic search with fallback to keyword.
- **RecommendationService**: like-based semantic reco → fallback to baseline.
- **ChatService**: session-aware (stores last 10 turns); greeting/guardrails; Qdrant + keyword contexts; LLM answer/verification; templated fallback.
- **Reminder/Interaction**: reminders CRUD; likes add/remove; sync liked_post_ids and like counts.
- **UserService**: user profile get/update; liked posts list.
- **Conversation/Message**: Mongo documents storing chat sessions and turns (used by ChatService).
- **LLMService & Vector Store**: HTTP client with fallbacks; Qdrant bootstrap/upsert/search helpers.
- **Ingest**: sources, normalize/tag/hash, LLM enrich, Mongo write, Qdrant upsert.

## 4) Data Model
- `posts`: title, url, posted_at, deadline_at, body, summary, tags[], college, department, audience_grade[], category, source, hash (unique), likes, timestamps.
- `users`: email (unique), college, department, grade, interests[], liked_post_ids[], preference_vector_id, created_at.
- `interactions`: user_id, post_id, type (`view|like|save`), ts, metadata.
- `reminders`: user_id, post_id, notify_at, channel (`email|kakao`), status, created_at.
- `conversations`: session store `{user_id?, summary?, created_at, updated_at}`.
- `messages`: `{conversation_id, role, content, created_at}`.
- Qdrant `notice_vectors`: single cosine vector (`QDRANT_VECTOR_SIZE`) + payload `{post_id, department, audience_grade, posted_at, deadline_at, tags, category, source}`.

## 5) API Surface (`/api` prefix)
| Method | Path | Purpose | Notes |
| --- | --- | --- | --- |
| GET | `/` | Service info | name/environment/message |
| GET | `/healthz` | Health | timezone + status |
| GET | `/feed` | Baseline feed | `category?`, excludes dummy/seed sources |
| GET | `/feed/reco-user` | Profile reco stub | signature mismatch → error until fixed |
| GET | `/feed/reco-likes` | Like-based reco | `user_id`, `limit`; semantic → fallback feed |
| GET | `/posts/{id}` | Post detail | raw Post document |
| GET | `/search` | Keyword/semantic | `q`, `mode=keyword|semantic`, `department?`, `grade?`; falls back to keyword |
| POST | `/likes` | Add like | `{user_id, post_id}` |
| DELETE | `/likes/{user_id}/{post_id}` | Remove like | idempotent |
| POST | `/reminders` | Create reminder | `{user_id, post_id, notify_at, channel}` |
| GET | `/reminders` | List reminders | `user_id`, pagination |
| POST | `/chat` | RAG QA (session-aware) | `{question, user_id?, department?, grade?, session_id?}` |
| GET | `/users/{user_id}` | User profile | email, college/department/grade, interests |
| PUT | `/users/{user_id}` | Update profile | `college/department/grade/interests` |
| GET | `/users/{user_id}/likes` | Liked posts | paginated feed-format items |
| GET | `/conversations/{session_id}/messages` | Session messages | recent turns (for UI) |
| POST | `/conversations/{session_id}/reset` | Reset session | clears history |

## 6) Ingest & Background
- Sources: dummy, local dataset, scholarship/internship samples, HTML crawler, catalog-driven adapters.
- Pipeline: fetch → normalize/tag/hash → dedupe → LLM summary/category → embed → Mongo_write → Qdrant upsert.
- APScheduler: optional ingest loop; manual run via `scripts/run_ingest.py`.

## 7) Config/Ops
- Key envs: Mongo/Qdrant connection, `QDRANT_VECTOR_SIZE`, `LLM_*`, `SCHEDULER_ENABLED`, `CRAWLER_SAMPLE_HTML`, `BOARD_CATALOG_*`.
- CORS: `http://localhost:5173`, `http://localhost:3000`.
- Vector collection bootstraps on first embed/search; pseudo vectors used when embedding keys are missing.

## 8) Known Gaps
- `/feed/reco-user` currently errors (FeedService signature mismatch). Align signature/filters before use.
- Advanced ranking, auth/rate limit, multi-channel notification delivery are not implemented; responses are simple list + meta.
