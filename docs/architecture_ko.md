# 지능형 공지 플랫폼 - 백엔드 아키텍처 (KOR)

## 1) 현재 범위
- `/api/*` 엔드포인트로 피드/검색/채팅/좋아요/리마인더를 제공하는 FastAPI 백엔드.
- MongoDB(Beanie)와 Qdrant를 사용하며, Qdrant 컬렉션은 최초 사용 시 자동 생성.
- LLM 요약/분류/임베딩/채팅 키가 없으면 결정론적 요약·임베딩으로 폴백하여 기능을 유지.
- 더미/로컬 데이터 + 샘플 HTML 크롤링으로 개발 환경 ingest를 실행하며, 필요 시 APScheduler로 주기 실행.

## 2) 런타임 구조
```
NoticeSource (dummy | local | catalog | HTML)
          │
          ▼
    IngestPipeline ──► Normalize/LLM ► Mongo `posts`
          │                           │
          │                           └─► Qdrant 벡터 업서트 (`notice_vectors`)
          │
          ▼
FastAPI (/api) ─► Services ─► Mongo 쿼리 + Qdrant 검색
                             └─► LLM 호출(옵션)
```
- `app/main.py`: CORS 적용, `/api` 라우터 포함, Mongo 연결 및 APScheduler 시작/정지 훅.
- `app/core/scheduler.py`: `SCHEDULER_ENABLED=true`일 때 ingest 파이프라인을 주기적으로 실행.

## 3) 모듈 역할
- **API 레이어** (`app/api/*`): 요청 검증과 단순 오케스트레이션.
- **FeedService**: `posted_at` 내림차순 피드, `category` 필터, 더미/시드 source 제외, 응답 포맷 변환.
- **SearchService**: Mongo 정규식 키워드 검색, LLM 임베딩 + Qdrant 기반 시맨틱 검색(실패 시 키워드 폴백).
- **RecommendationService**: 좋아요 기반 시맨틱 추천 → 실패 시 기본 피드; 프로필 추천 라우트는 스텁(아래 갭 참고).
- **ChatService**: Qdrant + 키워드 컨텍스트, 가드레일, LLM 답변 생성/검증, 불가 시 템플릿 응답.
- **Reminder / Interaction 서비스**: 리마인더 생성/조회, 좋아요 생성/삭제, 사용자 likedPost 캐시와 좋아요 카운트 동기화.
- **LLMService & Vector Store**: LLM HTTP 클라이언트와 폴백, Qdrant 컬렉션 부트스트랩/업서트/검색.
- **Ingest**: 소스 어댑터, 정규화/태깅/해싱, 중복 제거 후 LLM 요약/카테고리/임베딩 → Mongo 저장 → Qdrant 업서트.

## 4) 데이터 모델 (Mongo / Qdrant)
- `posts`: `title`, `url`, `posted_at`, `deadline_at`, `body`, `summary`, `tags[]`, `college`, `department`, `audience_grade[]`, `category`, `source`, `hash`(유니크), `likes`, 타임스탬프.
- `users`: `email`(유니크), `college`, `department`, `grade`, `interests[]`, `liked_post_ids[]`, `preference_vector_id`, `created_at`.
- `interactions`: `user_id`, `post_id`, `type`(`view|like|save`), `ts`, 선택 `metadata`.
- `reminders`: `user_id`, `post_id`, `notify_at`, `channel`(`email|kakao`), `status`, `created_at`.
- Qdrant `notice_vectors`: 단일 코사인 벡터(`QDRANT_VECTOR_SIZE`) + payload `{post_id, department, audience_grade, posted_at, deadline_at, tags, category, source}`.

## 5) API 개요 (`/api` prefix)
| Method | Path | 설명 | 비고 |
| --- | --- | --- | --- |
| GET | `/` | 서비스 정보 | 이름/환경/메시지 |
| GET | `/healthz` | 상태 확인 | 타임존 포함 |
| GET | `/feed` | 기본 피드 | `category?`, 더미 source 제외, `posted_at` 정렬, 축약된 아이템 필드 |
| GET | `/feed/reco-user` | 프로필 추천 스텁 | FeedService 시그니처 미스매치로 오류 상태 |
| GET | `/feed/reco-likes` | 좋아요 기반 추천 | `user_id`, `limit`; 시맨틱 결과 → 실패 시 피드 폴백 |
| GET | `/posts/{id}` | 게시물 단건 | Post 도큐먼트 원본 반환 |
| GET | `/search` | 키워드/시맨틱 검색 | `q`, `mode=keyword|semantic`, `department?`, `grade?`; 실패 시 키워드 폴백 |
| POST | `/likes` | 좋아요 추가 | `{user_id, post_id}` |
| DELETE | `/likes/{user_id}/{post_id}` | 좋아요 제거 | 멱등 |
| POST | `/reminders` | 리마인더 생성 | `{user_id, post_id, notify_at, channel}` |
| GET | `/reminders` | 리마인더 목록 | `user_id`, 페이지네이션 |
| POST | `/chat` | RAG 질의응답 | `{question, user_id?, department?, grade?}` |

## 6) Ingest & 백그라운드
- 소스: 더미, 로컬 더미 데이터셋, 장학/인턴십 샘플 어댑터, HTML 크롤러, 카탈로그 기반 어댑터.
- 파이프라인: fetch → normalize/tag/hash → 중복 스킵 → LLM 요약/카테고리 → 임베딩 → Mongo 저장 → Qdrant 업서트.
- APScheduler: ingest를 주기 실행(설정 시); 수동 실행은 `scripts/run_ingest.py`.

## 7) 설정/운영 포인트
- 주요 환경 변수: Mongo/Qdrant 연결, `QDRANT_VECTOR_SIZE`, `LLM_*` 베이스/키, `SCHEDULER_ENABLED`, `CRAWLER_SAMPLE_HTML`, `BOARD_CATALOG_*`.
- CORS: `http://localhost:5173`, `http://localhost:3000` 허용.
- 벡터 컬렉션은 최초 임베딩/검색 시 부트스트랩, 임베딩 키 미설정 시에도 폴백 벡터로 동작.

## 8) 알려진 갭
- `RecommendationService.profile_recommendations`가 `FeedService.get_feed`와 시그니처가 맞지 않아 `/feed/reco-user`는 현재 실행 시 오류가 발생함. 필터/시그니처 정리가 필요.
- 고급 랭킹, 인증/레이트 리밋, 멀티 채널 알림 발송 등은 아직 미구현이며, 응답은 단순 리스트+메타 수준임.
