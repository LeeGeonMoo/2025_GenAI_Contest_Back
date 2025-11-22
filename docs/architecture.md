# Intelligent Campus Notice Platform - Backend Architecture

## 1) Current Scope
- FastAPI app serving /api/* endpoints for feed, search, chat, likes, reminders, user profile.
- MongoDB (Beanie) + Qdrant; collections auto-create on first use.
- LLM calls optional; deterministic summary/embedding fallbacks keep flows working when keys are missing.
- Dev ingest uses dummy/local sources and optional HTML crawling; APScheduler can run the ingest loop.
  - Preferred dummy: docs/dummy_data/dummy_samples.txt (JSON) via LocalDummyJSONSource in scripts/run_ingest.py.
  - Legacy HTML dummy (docs/dummy_notices) can be regenerated with scripts/create_dummy_dataset.py if needed.

## 2) Runtime Architecture
NoticeSource (dummy | JSON | catalog | HTML)
          |
          v
    IngestPipeline -> Normalize/LLM -> Mongo posts
          |                           |
          |                           -> Vector upsert to Qdrant (notice_vectors)
          |
          v
FastAPI (/api) -> Services -> Mongo queries + Qdrant search
                             -> Optional LLM calls
- app/main.py: CORS, /api router, Mongo lifecycle, APScheduler hooks.
- app/core/scheduler.py: runs ingest pipeline on interval when SCHEDULER_ENABLED=true.

## 3) Modules
- API (app/api/*): validation and routing.
- FeedService: baseline feed by posted_at, category filter, excludes dummy/seed sources, formats response.
- SearchService: Mongo regex keyword; LLM embedding + Qdrant semantic with fallback to keyword.
- RecommendationService: like-based semantic reco; fallback to baseline.
- ChatService: session-aware (last 10 turns), greeting/guardrails, Qdrant + keyword contexts, LLM answer/verification, templated fallback.
- Reminder/Interaction: reminders CRUD; likes add/remove; sync liked_post_ids and like counts.
- UserService: profile get/update; liked posts list.
- Conversation/Message: Mongo documents storing chat sessions and turns.
- LLMService & Vector Store: HTTP client with fallbacks; Qdrant bootstrap/upsert/search helpers.
- Ingest: parse sources, normalize/tag/hash, LLM enrich, Mongo write, Qdrant upsert.

## 4) Data Model
- posts: title, url, posted_at, deadline_at, body, summary, tags[], college, department, audience_grade[], category, source, hash (unique), likes, timestamps.
- users: email (unique), college, department, grade, interests[], liked_post_ids[], preference_vector_id, created_at.
- interactions: user_id, post_id, type (view|like|save), ts, metadata.
- reminders: user_id, post_id, notify_at, channel (email|kakao), status, created_at.
- conversations: {user_id?, summary?, created_at, updated_at}.
- messages: {conversation_id, role, content, created_at}.
- Qdrant notice_vectors: single cosine vector (QDRANT_VECTOR_SIZE) + payload {post_id, department, audience_grade, posted_at, deadline_at, tags, category, source}.

## 5) API Surface (/api prefix)
- GET / : service info
- GET /healthz : health
- GET /feed : baseline feed (category?, excludes dummy/seed sources)
- GET /feed/reco-user : profile reco stub (signature mismatch -> error)
- GET /feed/reco-likes : like-based reco (user_id, limit; semantic -> fallback)
- GET /posts/{id} : post detail
- GET /search : keyword/semantic (q, mode=keyword|semantic, department?, grade?)
- POST /likes : add like ({user_id, post_id})
- DELETE /likes/{user_id}/{post_id} : remove like
- POST /reminders : create reminder ({user_id, post_id, notify_at, channel})
- GET /reminders : list reminders (user_id, pagination)
- POST /chat : RAG QA (session-aware) ({question, user_id?, department?, grade?, session_id?})
- GET /users/{id} : user profile
- PUT /users/{id} : update profile
- GET /users/{id}/likes : liked posts
- GET /conversations/{session_id}/messages : session messages
- POST /conversations/{session_id}/reset : reset session

## 6) Ingest & Background
- Sources: dummy, curated JSON dummy dataset (docs/dummy_data/dummy_samples.txt), scholarship/internship samples, HTML crawler, catalog-driven adapters.
- Pipeline: fetch -> normalize/tag/hash -> dedupe -> LLM summary/category -> embed -> Mongo write -> Qdrant upsert.
- APScheduler: optional ingest loop; manual run via scripts/run_ingest.py.

## 7) Config/Ops
- Key envs: Mongo/Qdrant connection, QDRANT_VECTOR_SIZE, LLM_*, SCHEDULER_ENABLED, CRAWLER_SAMPLE_HTML, BOARD_CATALOG_*. 
- CORS: http://localhost:5173, http://localhost:3000.
- Vector collection bootstraps on first embed/search; pseudo vectors used when embedding keys are missing.

## 8) Known Gaps
- /feed/reco-user currently errors (FeedService signature mismatch). Align signature/filters before use.
- Advanced ranking, auth/rate limit, multi-channel notification delivery are not implemented; responses are simple list + meta.
