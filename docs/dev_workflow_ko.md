# 개발 워크플로 (KOR)

## 자주 쓰는 명령
| 작업 | 명령 |
| --- | --- |
| 스택 실행 | `make dev-up` |
| 스택 중지 | `make dev-down` |
| 더미 공지 생성 | `docker compose exec api python scripts/create_dummy_dataset.py` |
| Ingest 실행 | `make ingest` (`docker compose exec api python scripts/run_ingest.py`) |
| LLM 결과 확인 | `docker compose exec api python scripts/peek_posts.py` |
| 시맨틱 검색 테스트 | `docker compose exec api python scripts/search_qdrant.py "질문"` |
| 테스트 | `make test` (`docker compose exec api pytest`) |
| API 로그 추적 | `make logs` |

## 환경 변수
```ini
LLM_SUMMARY_BASE=https://...
LLM_SUMMARY_KEY=sk-...
LLM_EMBEDDING_BASE=https://...
LLM_EMBEDDING_KEY=sk-... (비워두면 폴백)
QDRANT_VECTOR_SIZE=1536
BOARD_CATALOG_ENABLED=false   # 더미만 사용하는 경우
```
- Summary/Embedding 엔드포인트를 분리할 수 있습니다. 임베딩 키를 나중에 받을 계획이면 비워둔 채 fallback으로 두세요.
- `.env` 수정 후에는 `docker compose up -d --build` 로 컨테이너를 재기동해야 합니다.

## 검증 시나리오
1. `docker compose exec api python scripts/run_ingest.py`
2. Mongo에서 `db.posts.find({source:"local-dummy-dataset"}).limit(5)`
3. `docker compose exec api python scripts/peek_posts.py` 로 요약/카테고리 확인
4. `docker compose exec api python scripts/search_qdrant.py "장학금 안내"` 로 Qdrant 시맨틱 검색 테스트
5. `/feed`, `/search?mode=semantic`, `/docs` 등을 호출해 API 응답 확인

## 기타 팁
- Qdrant 차원이 바뀌면 컬렉션을 삭제한 뒤 ingest를 재실행하세요.
- Mongo 루트 계정: `docker compose exec mongo mongosh -u root -p root --authenticationDatabase admin`
- 카탈로그 기반 실제 크롤러를 사용하려면 `.env`에서 `BOARD_CATALOG_ENABLED=true` 로 변경하고 `docs/board_sources/catalog.json`을 구성합니다.
