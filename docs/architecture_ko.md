# 지능형 공지 플랫폼 백엔드 아키텍처 (KOR)

## 1. 서비스 목표
- 학내 여러 게시판을 한곳으로 통합해 학생이 “나와 관련 있는 공지”만 빠르게 확인하도록 지원
- 학과/학년/관심사/좋아요 정보를 이용해 개인 맞춤형 피드·추천·검색·챗봇·알림 제공
- 시맨틱 검색과 마감 리마인더로 정보 접근 불균형·기회 손실 최소화

## 2. 시스템 구성
```
외부 게시판 -> (Ingest) -> Normalize -> LLM 요약/임베딩
   |                                          |
   v                                          v
 MongoDB (posts/users/...)            Qdrant (notice_vectors)
            ^                                   ^
            |                                   |
        FastAPI 서비스 레이어 (feed/search/reco/chat/reminder)
```
- Ingest 파이프라인은 더미 HTML(또는 실제 크롤러) → 정규화 → LLM 요약/분류/임베딩 → Mongo/Qdrant 저장
- FastAPI는 인증/검증/캐싱을 담당하고, Feed/Search/Recommend/Chat/Reminders API를 제공
- APScheduler는 수집/재임베딩/알림 잡을 등록

## 3. 계층별 책임
| 계층 | 역할 |
| --- | --- |
| API | FastAPI 라우터, 요청 검증, 레이트 리밋 |
| Service | 피드 스코어링, 시맨틱 검색, 추천/챗봇 로직 |
| Pipelines | 크롤링, 정규화, 요약/임베딩, 인덱스 동기화 |
| Storage | MongoDB(구조화 데이터), Qdrant(임베딩), Redis(선택) |
| Scheduler | APScheduler (ingest/리마인더) |
| External | LLM API, 이메일/카톡 알림, OAuth |

## 4. 주요 모듈
1. **Ingest** – 게시판별 어댑터, HTML 파서, Dummy Dataset
2. **Normalize** – 중복 해시, 학과/학년 태깅, 요약 입력 준비
3. **LLM Service** – 요약/카테고리 분류/임베딩 API 호출(요약·임베딩 엔드포인트 분리)
4. **Vector Store** – Qdrant 컬렉션 생성/업서트/검색
5. **Feed/Search** – Mongo 필터 + Qdrant 시맨틱 검색 하이브리드
6. **Recommendation** – 프로필 기반 / 좋아요 기반 추천
7. **Chat (RAG)** – Qdrant Top-K + 요약 컨텍스트 + LLM 생성
8. **Notify** – `/reminders` API + APScheduler 디스패처

## 5. 데이터 흐름
1. **수집** – Dummy HTML 또는 실제 크롤러 → RawNotice 생성
2. **정규화** – Normalize + LLM 요약/분류 + 임베딩
3. **저장** – MongoDB `posts`, Qdrant `notice_vectors`
4. **제공** – Feed/Search/Recommend API로 클라이언트에 전달
5. **상호작용** – `/likes`, `/reminders`, `/interactions` 기록
6. **알림** – APScheduler가 리마인더 스케줄 실행

## 6. API 요약
| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET `/feed` | 기본 피드, 학과/학년 필터 |
| GET `/search` | 키워드/시맨틱 검색 (`mode` 파라미터) |
| GET `/feed/reco-user` | 프로필 기반 추천 |
| GET `/feed/reco-likes` | 좋아요 기반 추천 (`user_id` 필요) |
| GET `/posts/{id}` | 공지 상세 |
| POST `/likes` / DELETE `/likes/{user_id}/{post_id}` | 좋아요/해제 |
| POST `/chat` | RAG 챗봇 |
| POST `/reminders` / GET `/reminders` | 리마인더 등록/조회 |
| GET `/healthz`, `/docs` | 헬스 체크, Swagger UI |

## 7. 데이터 스키마 (요약)
```json
posts: {
  title, body, summary, category, tags,
  college, department, audience_grade[],
  source, hash, likes, posted_at, deadline_at
}
users: { email, department, grade, liked_post_ids[] ... }
interactions: { user_id, post_id, type, ts }
reminders: { user_id, post_id, notify_at, channel, status }
Qdrant payload: { post_id, department, audience_grade, tags, dates }
```

## 8. 피드/추천 스코어
```
S = w_dept*DeptMatch + w_grade*GradeMatch + w_deadline*DeadlineBoost + w_recency*RecencyDecay
```
좋아요 기반 추천은 사용자 좋아요 임베딩 평균과 후보 벡터 유사도를 사용. 검색은 Mongo 텍스트 점수 + Qdrant 코사인 점수를 가중합.

## 9. 백그라운드 잡
- Dummy Dataset 혹은 실제 크롤러 ingest
- 모델 교체 시 재임베딩
- 리마인더 디스패처
- Preference Updater (좋아요/조회 이벤트 반영)

## 10. 운영/보안
- docker-compose (개발), EC2+Nginx (배포)
- `.env`/Secrets Manager로 환경 변수 관리
- 구조화 로그 + Prometheus + `/healthz`
- SNU OAuth + JWT, 레이트리밋, PII 최소 수집

## 11. 품질 지표
- 검색/추천 CTR, NDCG, 다양성, D-3 도달률
- 챗봇: 근거 포함률, 응답지연
- 파이프라인: 수집 성공률, 중복률, 처리 지연

## 12. 단계별 진행
1. FastAPI + Mongo/Qdrant + APScheduler 스캐폴딩
2. 모델 정의, 인덱스/시드 스크립트
3. Dummy/실제 ingest 파이프라인
4. Feed/Search/Recommend API 구현 + 테스트
5. RAG 챗봇, 알림 채널 통합
6. 실제 크롤러/어댑터 확장, 운영 모니터링 적용
