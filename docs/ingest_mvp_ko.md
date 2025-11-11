# Ingest MVP 사용 가이드 (KOR)

## 개요
- Dummy HTML 또는 실제 게시판을 수집 → 정규화 → LLM 요약/분류/임베딩 → Mongo/Qdrant 저장까지 한 번에 수행하는 파이프라인입니다.
- `LocalDummyDatasetSource` 덕분에 실제 크롤러 없이도 LLM 파이프라인을 검증할 수 있습니다.

## 구성 요소
- `app/ingest/base.py` – RawNotice/NormalizedNotice 데이터 모델과 소스 프로토콜
- `app/ingest/sources/local_dummy_dataset.py` – `docs/dummy_notices` 디렉터리를 읽어 테스트 데이터를 공급
- `app/ingest/sources/wordpress.py` 등 – 공통 템플릿 파서
- `app/ingest/pipeline.py` – 정규화, LLM 요약/분류/임베딩, Mongo/Qdrant 저장
- `app/services/llm_service.py` – 요약/카테고리/임베딩 API 호출
- `app/services/vector_store.py` – Qdrant 컬렉션 생성/업서트/검색
- `scripts/run_ingest.py` – 파이프라인 실행 스크립트

## 실행 절차
1. `.env` 설정  
   ```ini
   LLM_SUMMARY_BASE=https://...
   LLM_SUMMARY_KEY=sk-...
   LLM_EMBEDDING_BASE=https://...
   LLM_EMBEDDING_KEY=sk-... (없으면 비워도 됨)
   QDRANT_VECTOR_SIZE=임베딩 차원(예: 1536)
   BOARD_CATALOG_ENABLED=false   # dummy만 쓰는 경우
   ```
2. 컨테이너 기동  
   ```bash
   docker compose up -d --build
   ```
3. 더미 공지 생성 (선택)  
   ```bash
   docker compose exec api python scripts/create_dummy_dataset.py
   ```
4. 파이프라인 실행  
   ```bash
   docker compose exec api python scripts/run_ingest.py
   ```
   - 출력 예: `{'inserted': 20, 'skipped': 28, 'vectorized': 20}`
   - LLM 설정이 올바르면 fallback 경고가 사라집니다.
5. 결과 확인  
   - Mongo: `docker compose exec mongo mongosh -u root -p root --authenticationDatabase admin`
     ```javascript
     use notisnu
     db.posts.find({source:"local-dummy-dataset"}, {title:1, summary:1, category:1}).limit(5)
     ```
   - Qdrant: `docker compose exec qdrant curl -s http://localhost:6333/collections/notice_vectors | jq .`
   - 빠르게 확인하려면 `docker compose exec api python scripts/peek_posts.py`

## 카탈로그 비활성화
- `.env`에서 `BOARD_CATALOG_ENABLED=false` 로 두면 실제 게시판 어댑터는 호출되지 않고 더미 데이터만 수집됩니다.
- 실제 크롤러를 붙이고 싶을 때 `true`로 전환하고 `docs/board_sources/catalog.json` 을 업데이트하면 됩니다.

## 주의 사항
- 임베딩 모델 차원과 Qdrant 컬렉션 설정(`QDRANT_VECTOR_SIZE`)을 반드시 맞추세요.
- LLM 키가 없으면 fallback 로직(해시 기반 요약/임베딩)이 실행되어 품질이 낮아집니다.
- Qdrant 컬렉션을 재생성하려면 `curl -X DELETE http://localhost:6333/collections/notice_vectors` 실행 후 ingest를 다시 돌리세요.

## 다음 단계
- 실제 게시판 어댑터(template별 WordPress/table/API 등)를 추가해 카탈로그를 확장
- APScheduler로 ingest/리마인더 자동화
- `/feed`, `/search`, `/feed/reco-*`, `/chat` 등 API 연동 및 클라이언트 검증
