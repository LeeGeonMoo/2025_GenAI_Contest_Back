# 지능형 공지 플랫폼 - 백엔드 아키텍처 (KOR)

## 1) 현재 범위
- /api/* 엔드포인트로 피드/검색/챗봇/좋아요/리마인더/사용자 프로필 제공.
- MongoDB(Beanie)+Qdrant, 컬렉션은 최초 사용 시 자동 생성.
- LLM 키 미설정 시 요약/임베딩을 결정론적 폴백으로 생성하여 흐름 유지.
- 개발용 더미/로컬 소스 + HTML 크롤링, 필요 시 APScheduler로 주기 실행.
  - 기본 더미: docs/dummy_data/dummy_samples.txt(JSON) → LocalDummyJSONSource (scripts/run_ingest.py).
  - HTML 더미(docs/dummy_notices)는 scripts/create_dummy_dataset.py로 재생성해 사용 가능.

## 2) 런타임 구조
```
NoticeSource (dummy | JSON | catalog | HTML)
          |
          v
    IngestPipeline → Normalize/LLM → Mongo posts
          |                           |
          |                           → Qdrant 업서트 (notice_vectors)
          |
          v
FastAPI (/api) → Services → Mongo 쿼리 + Qdrant 검색
                             → (옵션) LLM 호출
```
- app/main.py: CORS, /api 라우터, Mongo 라이프사이클, APScheduler 훅.
- app/core/scheduler.py: SCHEDULER_ENABLED=true 시 ingest 파이프라인 주기 실행.

## 3) 모듈
- API (app/api/*): 검증/라우팅.
- FeedService: posted_at 정렬, category 필터, 더미/시드 source 제외, 포맷팅.
- SearchService: Mongo 정규식 키워드, LLM 임베딩 + Qdrant 시맨틱(실패 시 키워드).
- RecommendationService: 좋아요 기반 시맨틱 → 실패 시 기본 피드.
- ChatService: 세션(최근 10턴, intent/meta 저장), 인사/종료/가드레일, Qdrant+키워드 컨텍스트, 최근 citations 기반 follow-up, LLM 답변/검증, 템플릿 폴백, JSON 파싱 보강.
- Reminder/Interaction: 리마인더 CRUD, 좋아요 생성/삭제, liked_post_ids/like 카운트 동기화.
- UserService: 프로필 조회/수정, 좋아요 게시물 목록.
- Conversation/Message: 세션/메시지 Mongo 도큐먼트.
- LLMService & Vector Store: HTTP 클라이언트(폴백 포함), Qdrant 부트스트랩/업서트/검색.
- Ingest: 소스 파싱, 정규화/태깅/해시, LLM 요약/분류/임베딩, Mongo 저장, Qdrant 업서트.

## 4) 데이터 모델
- posts: title, url, posted_at, deadline_at, body, summary, tags[], college, department, audience_grade[], category, source, hash(유니크), likes, 타임스탬프.
- users: email(유니크), college, department, grade, interests[], liked_post_ids[], preference_vector_id, created_at.
- interactions: user_id, post_id, type(view|like|save), ts, metadata.
- reminders: user_id, post_id, notify_at, channel(email|kakao), status, created_at.
- conversations: {user_id?, summary?, created_at, updated_at}.
- messages: {conversation_id, role, content, created_at}.
- Qdrant notice_vectors: 단일 코사인 벡터(QDRANT_VECTOR_SIZE) + payload {post_id, department, audience_grade, posted_at, deadline_at, tags, category, source}.

## 5) API 개요 (/api prefix)
- GET / : 서비스 정보 (이름/환경/메시지)
- GET /healthz : 상태 확인 (타임존 포함)
- GET /feed : 기본 피드 (category?, 더미 source 제외)
- GET /feed/reco-user : 프로필 추천 스텁 (FeedService 시그니처 미스매치로 오류 상태)
- GET /feed/reco-likes : 좋아요 기반 추천 (user_id, limit; 시맨틱 -> 피드 폴백, 모든 아이템에 semantic_score + similar likes 기반 reason 포함)
- GET /posts/{id} : 게시물 단건 (Post 도큐먼트 원본)
- GET /search : 키워드/시맨틱 (q, mode=keyword|semantic, department?, grade?; 실패 시 키워드)
- POST /likes : 좋아요 추가 ({user_id, post_id})
- DELETE /likes/{user_id}/{post_id} : 좋아요 제거 (멱등)
- POST /reminders : 리마인더 생성 ({user_id, post_id, notify_at, channel})
- GET /reminders : 리마인더 목록 (user_id, 페이지네이션)
- POST /chat : RAG QA(세션) ({question, user_id?, department?, grade?, session_id?})
- GET /users/{user_id} : 사용자 프로필 (email, 단과/학과, 학년, interests)
- PUT /users/{user_id} : 사용자 프로필 수정 (college/department/grade/interests)
- GET /users/{user_id}/likes : 좋아요 게시물 (페이징, feed 포맷)
- GET /conversations/{session_id}/messages : 세션 메시지 (최근 턴)
- POST /conversations/{session_id}/reset : 세션 초기화 (히스토리 삭제)

## 6) Ingest & 백그라운드
- 소스: 더미, 기본 JSON 더미(docs/dummy_data/dummy_samples.txt), 장학/인턴십 샘플, HTML 크롤러, 카탈로그 기반 어댑터.
- 파이프라인: fetch → normalize/tag/hash → dedupe → LLM summary/category → embed → Mongo write → Qdrant upsert.
- APScheduler: ingest 주기 실행(설정 시); 수동 실행은 scripts/run_ingest.py.

## 7) 설정/운영
- 주요 env: Mongo/Qdrant 연결, QDRANT_VECTOR_SIZE, LLM_*, SCHEDULER_ENABLED, CRAWLER_SAMPLE_HTML, BOARD_CATALOG_*.
- CORS: http://localhost:5173, http://localhost:3000.
- 벡터 컬렉션은 최초 임베딩/검색 시 부트스트랩; 임베딩 키 미설정 시 pseudo 벡터 사용.

## 8) 알려진 갭
- /feed/reco-user 시그니처 미스매치로 현재 오류 상태 → FeedService/라우트 정리가 필요.
- 고급 랭킹, 인증/레이트 리밋, 멀티 채널 알림 발송 미구현 → 단순 리스트+메타 응답 수준.
