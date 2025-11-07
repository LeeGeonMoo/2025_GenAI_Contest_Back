# Intelligent Campus Notice Platform - Backend Architecture

## 1. Mission & Requirements
- **Goal**: build an intelligent platform that consolidates fragmented campus notices and serves personalized feeds, search, chat answers, and reminders based on department, grade, interests, and explicit feedback.
- **Value Propositions**
  - Remove information asymmetry: students see only relevant notices with one visit.
  - Reduce search time via natural-language/semantic retrieval.
  - Minimize opportunity loss by combining preference-based ranking with deadline reminders.

## 2. System Overview
```
+----------------+          +-----------+          +-----------+
| External Boards| --crawl->| Ingest    |--clean-->|
| (dept APIs etc)|          | Service   |          | Normalize |
+----------------+          +-----------+          +-----------+
                                                   |
                                                   v
                                            +-------------+
                                            | Embedder    |--> LLM API
                                            +-------------+
                                                   |
                        +--------------------------+---------------------+
                        |                                                |
                +---------------+                           +---------------------+
                |   MongoDB     |<----read/write----------->|   Service Layer     |
                | posts/users...|                           | (FastAPI feed/search|
                +---------------+                           |   recommend/chat)   |
                        ^                                     +---------+---------+
                        |                                               |
                        | metadata/query                                | vector search
                        |                                               v
                        |                                     +---------------------+
                        +-------------------------------------|       Qdrant        |
                                                              |   notice vectors    |
                                                              +---------------------+

Background jobs (APScheduler): ingest, re-embedding, reminders.
Email/Kakao adapters are called from the Notify service.
```

## 3. Layered Architecture
| Layer | Responsibility |
| --- | --- |
| **API (FastAPI)** | Auth, validation, rate limit, REST/RPC surface, response caching |
| **Service/Core** | feed scoring, semantic search orchestration, recommend/chat logic |
| **Pipelines** | ingest, normalize, summarization, embedding, index sync |
| **Storage** | MongoDB (structured data/events), Qdrant (vectors), Redis (optional cache) |
| **Schedulers** | APScheduler distributed jobs: crawl, embedding refresh, reminder |
| **External** | LLM/Embedding API, Email/Kakao providers, OAuth (SNU) |

## 4. Module Details
1. **Ingest**
   - Board-specific crawler adapters (HTML, RSS, REST).
   - Emits unified DTOs into a queue (Kafka/SQS optional) or directly to Normalize.
2. **Normalize**
   - Dedup hash (`hash = sha256(title+body+posted_at)`).
   - Department/grade tagging rules plus ML classifier fallback.
   - Body cleanup, summary prompt to LLM.
3. **Embed**
   - Store body/summary multi-vectors (dual collection or multi-vector field).
   - Update user preference vectors via running average of liked notice embeddings.
4. **Retriever/Search**
   - Hybrid approach: Mongo text + Qdrant semantic with Reciprocal Rank Fusion.
   - Always dual-query; `mode` toggles weighting (`keyword` vs `semantic` emphasis).
5. **Ranking/Feed**
   - Baseline feed filters by department/grade and boosts recency/deadlines.
   - Recommendation services accept user context and score candidate sets.
6. **Chat (RAG)**
   - Query -> Qdrant Top-k -> context compression -> LLM answer with citations.
   - Guardrail: include title/link evidence; fallback message if confidence low.
7. **Notify**
   - Reminder schedule stored in DB, APScheduler worker evaluates D-3/D-1 windows.
   - Channel adapters abstract Email/Kakao integrations.
   - Board catalog + adapter registry (`docs/board_sources`, `app/ingest/adapters.py`) drive ingest targets per college/department.

## 5. End-to-End Data Flow
1. **Collect**: boards -> Ingest -> Normalize.
2. **Store**:
   - MongoDB `posts` keeps metadata/body/tags.
   - Qdrant `notice_vectors` stores embeddings + payload (post_id, dept, grade, tags, dates).
3. **Serve**:
   - Feed/Search combine Mongo filters with Qdrant semantic scores.
   - Recommend uses user profile and preference vectors.
   - Chat uses the RAG pipeline to build answers.
4. **Interact**:
   - Likes/saves/views logged in `interactions`; trigger preference updates.
5. **Notify**:
   - `/reminders` creates jobs; APScheduler dispatches when due and records status.

## 6. API Surface (summary)
| Method | Path | Purpose | Key params/body |
| --- | --- | --- | --- |
| GET | `/feed` | Baseline personalized feed | `department`, `grade`, `page`, `page_size` |
| GET | `/search` | Hybrid keyword/semantic search | `q`, `mode`, `department`, `grade`, `page` |
| GET | `/feed/reco-user` | Profile-driven recommendation | `department`, `grade`, `limit` |
| GET | `/feed/reco-likes` | Like-based semantic recommendation | `user_id`, `limit` |
| GET | `/posts/{id}` | Notice detail | path `id` |
| POST | `/likes` | Add like (pre-auth placeholder) | `{user_id, post_id}` |
| DELETE | `/likes/{user_id}/{post_id}` | Remove like | path `user_id`, `post_id` |
| POST | `/chat` | Notice RAG chatbot | `{query, user_context}` |
| POST | `/reminders` | Schedule reminder | `{user_id, post_id, notify_at, channel}` |
| GET | `/reminders` | List reminders | pagination params |
| POST | `/auth/callback` | SNU OAuth callback | token exchange payload |
| GET | `/healthz`, `/metrics` | Health and Prometheus metrics | - |

### Response Contract
- Store timestamps in UTC ISO-8601; UI converts to Asia/Seoul.
- Include `meta` (pagination, latency, trace_id) for observability.
- Feed/search items expose scoring metadata (recency/deadline source) for explainability.

## 7. Data Model (MongoDB & Qdrant)
### MongoDB collections
```json
posts: {
  _id: ObjectId,
  title: string,
  url: string,
  posted_at: ISODate,
  deadline_at: ISODate|null,
  body: string,
  summary: string,
  tags: [string],
  college: string,
  department: string,
  audience_grade: [string],
  category: string,
  hash: string,
  likes: int,
  updated_at: ISODate,
  created_at: ISODate
}

users: {
  _id: ObjectId,
  email: string,
  college: string,
  department: string,
  grade: string,
  interests: [string],
  liked_post_ids: [ObjectId], // optional cache
  preference_vector_id: string, // Qdrant vector id
  created_at: ISODate
}

interactions: {
  _id: ObjectId,
  user_id: ObjectId,
  post_id: ObjectId,
  type: "view"|"like"|"save",
  ts: ISODate,
  metadata: {}
}

reminders: {
  _id: ObjectId,
  user_id: ObjectId,
  post_id: ObjectId,
  notify_at: ISODate,
  channel: "email"|"kakao",
  status: "scheduled"|"sent"|"failed",
  created_at: ISODate
}
```

### Qdrant collections
- `notice_vectors`
  - `vectors`: `{body: 1536, summary: 768}` (example dimensions)
  - `payload`: `{ post_id, department, audience_grade, posted_at, deadline_at, tags, category }`
- `user_preferences`
  - stores averaged like embeddings per user (optional; can compute on the fly).

## 8. Scoring Logic
### Baseline feed
```
S = w_dept * DeptMatch
  + w_grade * GradeMatch
  + w_interest * InterestOverlap
  + w_deadline * DeadlineBoost
  + w_recency * RecencyDecay
```
- `DeptMatch`, `GradeMatch`: binary or soft (exact=1, college-level=0.5).
- `DeadlineBoost`: `exp(-days_until_deadline / tau)`; expired -> large negative penalty.
- `RecencyDecay`: `exp(-hours_since_posted / lambda)`.

### Like-based recommendation
```
S_like = alpha * cosine(user_like_vector, post_vector)
       + beta  * DeadlineBoost
       - gamma * SeenPenalty
```
- `user_like_vector`: running mean of liked notice vectors.
- `SeenPenalty`: reduces score for already exposed/seen posts.

### Search ranking
- Blend Mongo keyword score and Qdrant semantic score: `score = k1*keyword + k2*semantic`.
- Reciprocal Rank Fusion stabilizes mixed result ordering.

## 9. Background Jobs & Pipelines
- **Crawler jobs**: per-board cadence (10m~1h) with retry queues on failure.
- **Embedding refresh**: batch job when model version changes.
- **Reminder dispatcher**: runs every minute; sends when `notify_at - now <= delta`.
- **Preference updater**: reacts to like/unlike events to refresh vectors.
- Log every job run to Mongo `jobs_log` or OpenSearch; expose `/jobs/last-run` for ops.

## 10. Operations & Security
- **Deployment**: docker-compose for dev; EC2 + Nginx (or ECS/Kubernetes) for prod.
- **Configuration**: `.env` per environment, synced with Secrets Manager.
- **Observability**: structured JSON logs, Prometheus metrics (request latency, Qdrant latency, job success).
- **Timezone policy**: persist UTC, return `X-Timezone: Asia/Seoul` header.
- **Security**:
  - SNU OAuth (Google Workspace) + JWT sessions.
  - Rate limiting via Redis token bucket.
  - Minimal PII retention, encrypt sensitive fields (email).

## 11. Quality Metrics
- **Search**: CTR@K, NDCG@K, time to first click.
- **Recommendation**: CTR@K, save rate@K, diversity, D-3 reminder reach.
- **Chatbot**: citation coverage, hallucination rate, latency.
- **Pipelines**: ingest success ratio, duplicate ratio, embedding processing delay.

## 12. Next Implementation Steps
1. Scaffold FastAPI project with Mongo ODM (Pydantic models, Beanie/Motor), Qdrant client, APScheduler.
2. Define data models and migration/index scripts (seeding departments, TTL indexes).
3. Build ingest/normalize MVP covering at least one HTML crawler and one API source.
4. Implement Feed/Search/Recommend endpoints plus unit/integration tests.
5. Deliver RAG chatbot PoC (Qdrant + LLM) with guardrail policy.
6. Integrate Email/Kakao channels and exercise reminder scheduling end-to-end.
