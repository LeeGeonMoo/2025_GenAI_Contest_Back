# 게시판 카탈로그 가이드 (KOR)

## 1. catalog.json 구조
```json
[
  {
    "id": "snuc_notice",
    "college": "공과대학",
    "department": "학사과",
    "url": "https://snuc.snu.ac.kr/...",
    "template": "wordpress_board",
    "requires_auth": false,
    "options": {
      "pagination": { "type": "path", "start": 1, "max_pages": 2 }
    }
  }
]
```
- `template` 값에 따라 어댑터를 매핑 (`app/ingest/adapters.py`)
- `options.pagination` 으로 `/page/{n}` 또는 `?page=n` 등을 정의
- `BOARD_CATALOG_ENABLED=true` 로 설정해야 `scripts/run_ingest.py` 가 이 목록을 불러옵니다 (기본값은 false).

## 2. 사용 흐름
1. `docs/board_sources/catalog.json` 에 새 게시판을 추가
2. 템플릿에 맞는 파서를 구현하거나 기존 어댑터를 사용
3. `.env`에서 `BOARD_CATALOG_ENABLED=true` 로 설정 (실제 크롤러가 필요할 때만)
4. `docker compose exec api python scripts/run_ingest.py`

## 3. Dummy Dataset
- 실제 크롤러 전에 LLM/추천 기능을 검증할 수 있도록 `docs/dummy_notices/notice_*.html`이 제공되며, `LocalDummyDatasetSource`가 항상 이 데이터를 로드합니다.
- Dummy 모드만 쓰려면 `BOARD_CATALOG_ENABLED=false` 로 두고, 필요 시 `scripts/create_dummy_dataset.py` 로 데이터를 다시 생성하면 됩니다.

## 4. 어댑터 확장
- WordPress 계열: `WordpressListSource`
- HTML 맞춤형: `SNUScholarshipHTMLSource` 등
- 추가 템플릿(table, API 등)을 만들 때는 `app/ingest/sources/` 에 클래스를 추가하고 `app/ingest/adapters.py` 에 등록하면 됩니다.

## 5. 주의사항
- 게시판별 로그인/인증이 필요한 경우 `requires_auth` 플래그를 이용해 별도 처리 로직을 넣어야 합니다.
- pagination이 잘못 설정되면 404가 반복될 수 있으니, `_iter_page_urls` 로직과 옵션을 맞춰 주세요.
