# NotiSNU Backend – Quick Start (Docker)

이 문서는 저장소를 그대로 클론한 뒤 Docker 환경에서 실행하는 방법을 정리합니다.  
Dummy 공지를 LLM 요약/분류/임베딩과 함께 MongoDB/Qdrant에 저장한 후, `/feed`·`/search` 등의 API를 바로 확인할 수 있습니다.

---

## 1. 사전 준비
- Docker & Docker Compose가 설치되어 있어야 합니다.
- 클론한 프로젝트 루트에서 모든 명령을 실행합니다.

```bash
git clone <repo-url>
cd notisnu
```

---

## 2. 환경 변수 설정
`.env.example`을 참고해 `.env`를 만듭니다.

```bash
cp .env.example .env
```

필수로 채워야 할 항목:
```ini
# 요약/분류에 사용할 LLM (OpenAI 호환 또는 호환 API)
LLM_SUMMARY_BASE=https://factchat-cloud.mindlogic.ai/v1/api/openai
LLM_SUMMARY_KEY=...
LLM_SUMMARY_MODEL=gpt-5-chat-latest      # 원하는 모델명

# 임베딩 (추후 필요 시; 지금은 비워도 됨)
LLM_EMBEDDING_BASE=https://api.openai.com/v1
LLM_EMBEDDING_KEY=sk-...                 # 아직 없다면 빈칸
LLM_EMBEDDING_MODEL=text-embedding-3-large

# Qdrant 벡터 차원 (임베딩 모델과 맞춰야 함)
QDRANT_VECTOR_SIZE=1536

# 실제 게시판 크롤러를 아직 쓰지 않을 경우 false
BOARD_CATALOG_ENABLED=false

# RAG 챗봇 응답용 (요약 엔드포인트와 분리 가능)
LLM_CHAT_BASE=https://api.openai.com/v1
LLM_CHAT_KEY=sk-...
LLM_CHAT_MODEL=gpt-4o-mini
LLM_CHAT_MAX_TOKENS=600
LLM_CHAT_TIMEOUT=20
```
임베딩 키가 없으면 임베딩은 fallback 벡터를 사용합니다.

---

## 3. 컨테이너 실행
```bash
docker compose up -d --build
```
정상 기동 후 `http://localhost:8000` 에서 API를 확인할 수 있습니다.

---

## 4. Dummy 데이터 생성 + Ingest
1. (선택) Dummy 공지를 다시 생성:
   ```bash
   docker compose exec api python scripts/create_dummy_dataset.py
   ```
2. Ingest 실행 (LLM 요약/분류/임베딩 → Mongo/Qdrant 저장):
   ```bash
   docker compose exec api python scripts/run_ingest.py
   ```
   - `{'inserted': N, 'skipped': M, 'vectorized': N}` 출력이 보이면 성공입니다.

---

## 5. 데이터 확인 방법
- Mongo 요약/카테고리:
  ```bash
  docker compose exec api python scripts/peek_posts.py
  ```
  최근 저장된 공지 제목/카테고리/요약/본문 일부를 출력합니다.

- 시맨틱 검색 테스트:
  ```bash
  docker compose exec api python scripts/search_qdrant.py "장학금 신청 마감 안내"
  ```
  Qdrant에서 유사 공지를 찾아 제목/요약을 보여줍니다.

- 직접 Mongo 접속:
  ```bash
  docker compose exec mongo mongosh -u root -p root --authenticationDatabase admin
  use notisnu
  db.posts.find({source:"local-dummy-dataset"}).limit(5)
  ```

- Qdrant 컬렉션 상태:
  ```bash
  docker compose exec qdrant curl -s http://localhost:6333/collections/notice_vectors | jq .
  ```

---

## 6. API 사용
- `http://localhost:8000/docs` 에 Swagger UI가 활성화되어 있습니다.
- 주요 엔드포인트:
  - `GET /feed` – 기본 피드
  - `GET /search?q=키워드&mode=semantic` – 시맨틱 검색
  - `GET /feed/reco-user`, `GET /feed/reco-likes`
  - `GET /posts/{id}`
  - `POST /likes`, `POST /reminders`
  - `POST /chat` (공지 기반 RAG 챗봇, DB 범위를 벗어나면 거절)

### `/chat` 흐름 요약
- MongoDB 키워드 검색과 Qdrant 벡터 검색 결과를 가중 결합해 질문과 가장 연관된 공지 3~5건을 선별합니다.
- 욕설·날씨 등 공지와 무관한 질문, 혹은 관련 공지를 찾지 못한 경우에는 이유를 명시한 친절한 거절 메시지를 돌려줍니다.
- LLM이 생성한 1차 답변은 “질문 의도에 부합하는지”를 재검수하는 2차 LLM 패스로 한 번 더 필터링합니다.
- LLM 호출이 불가능하면 수집된 공지를 `- 제목 (학과, 날짜) + 주요 내용` 형태로 요약해 최소한의 정보를 제공합니다.

---

## 7. 테스트 & 기타 명령
```bash
docker compose exec api pytest             # 테스트 실행
make dev-down                              # 컨테이너 종료
make logs                                  # API 로그 tail
```

---

## 8. 실제 게시판 크롤러를 사용할 경우
1. `docs/board_sources/catalog.json` 에 게시판 정보를 등록합니다.
2. `.env` 에서 `BOARD_CATALOG_ENABLED=true` 로 변경합니다.
3. `docker compose exec api python scripts/run_ingest.py` 를 실행하면 카탈로그에 등록된 게시판 어댑터가 자동 실행됩니다. (현재 템플릿별 어댑터는 기본 WordPress + HTML 샘플만 제공됩니다.)

---

## 9. 트러블슈팅
- LLM 관련 `Falling back ... not configured` 메시지가 나온다면 `.env` 에 summary/embedding 키가 채워져 있는지 확인하세요.
- Qdrant에서 `expected dim 768, got 1536` 오류가 나면 `QDRANT_VECTOR_SIZE` 와 임베딩 모델 차원이 일치하는지 확인하고, 기존 컬렉션을 삭제 후 재생성하세요.
- Mongo 연결 시 인증 오류가 나면 `mongosh -u root -p root --authenticationDatabase admin` 으로 접속하세요.

---

이 가이드대로 실행하면 더미 데이터만으로도 LLM 요약/분류/임베딩, MongoDB/Qdrant 저장, Feed/Search/추천 API를 모두 검증할 수 있습니다. 필요 시 `scripts/*.py` 테스트 스크립트는 자유롭게 삭제해도 됩니다.
