# API Overview (current code)

- Base URL: `/api`
- CORS: `http://localhost:5173`, `http://localhost:3000`
- Auth: none (dev only)
- All timestamps are ISO strings from Mongo/Qdrant.

## Endpoints
- `GET /` — service info `{service, environment, message}`
- `GET /healthz` — `{status, service, timezone}`
- `GET /feed`
  - Query: `category?`, `page`(default 1), `page_size`(default 20, max 100)
  - Excludes sources: `seed_posts`, `dummy-source`, `scholarship-board`, `internship-board`, `scholarship-source`, `internship-source`, empty
  - Returns items with `id`, `title`, `tags`, `category`, `source` (list of `{name,url}`), `posted_at`, `deadline`, plus pagination meta (`total`, `page`, `page_size`, `total_pages`)
- `GET /feed/reco-user`
  - Intended profile-based feed, but currently calls `FeedService.get_feed` with unsupported args → runtime error until signature is fixed.
- `GET /feed/reco-likes`
  - Query: `user_id`, `limit` (default 10, max 50)
  - If the user has liked posts and embeddings are available, returns posts with `semantic_score` and `meta.mode = "likes-semantic"`.
  - Otherwise falls back to baseline feed with `meta.mode = "likes-fallback"`.
- `GET /posts/{post_id}` — returns the raw `Post` document (all fields).
- `GET /search`
  - Query: `q` (required), `mode=keyword|semantic` (default `keyword`), `department?`, `grade?`, `page`, `page_size`
  - `semantic`: embed query → Qdrant search → attach `semantic_score`; falls back to keyword when embedding/search fails.
  - `keyword`: case-insensitive regex over `title|summary|body`; meta includes `total/page/page_size`.
- `POST /likes` — body `{user_id, post_id}`; updates interaction + like count.
- `DELETE /likes/{user_id}/{post_id}` — removes the like if present.
- `POST /reminders` — body `{user_id, post_id, notify_at, channel("email"|"kakao")}`; creates a reminder.
- `GET /reminders` — query `user_id`, `page`, `page_size`; returns reminders + pagination meta.
- `POST /chat`
  - Body: `{question (1~400 chars), user_id?, department?, grade?, session_id?}`
  - Guardrails for abuse/out-of-scope → refusal message.
  - Session-aware: returns/accepts `meta.session_id`; greeting is handled without search.
  - Retrieves Qdrant + keyword contexts, generates LLM answer with citations, verifies answer; falls back to templated answer if LLM unavailable or verification fails.
  - Response: `{answer_md/answer, citations[id list], citation_details[], notices[], meta{question, refused, reason, source, session_id}}`.
- `GET /users/{user_id}` — user profile (email, college/department/grade, interests, timestamps).
- `PUT /users/{user_id}` — update profile fields (`college/department/grade/interests` subset).
- `GET /users/{user_id}/likes` — liked posts in feed item format, paginated.
- `GET /conversations/{session_id}/messages` — recent messages for a session.
- `POST /conversations/{session_id}/reset` — clears a chat session.

## Example responses
`GET /api/feed`:
```json
{
  "items": [
    {
      "id": "6554...",
      "title": "Dummy 장학 안내",
      "tags": ["장학", "신청"],
      "category": "장학",
      "source": [{"name": "dummy-source", "url": null}],
      "posted_at": "2024-11-14T12:00:00Z",
      "deadline": "2024-11-20T12:00:00Z"
    }
  ],
  "meta": {"total": 1, "page": 1, "page_size": 20, "total_pages": 1}
}
```

`POST /api/chat` (success path):
```json
{
  "answer": "답변 내용...",
  "citations": ["6554..."],
  "notices": [{"post_id": "6554...", "title": "...", "score": 0.73, "...": "..."}],
  "meta": {"question": "장학금 언제 신청해?", "refused": false, "reason": "success", "source": "llm"}
}
```

## Known caveats
- `/feed/reco-user` currently errors because `RecommendationService` passes `department/grade` into `FeedService.get_feed`, which only accepts `category`. Fix the signature or adjust the route before using.
- Search meta totals are counted after department/grade filters, not by query matching.
