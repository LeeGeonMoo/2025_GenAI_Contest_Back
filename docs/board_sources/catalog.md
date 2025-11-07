# SNU Board Catalog (Temporary)

| ID | College / Unit | Department / Office | URL | Format Hint | Auth | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `snuc_notice` | 공과대학 | 공과대학 학사과 (College of Engineering) | https://snuc.snu.ac.kr/%ea%b3%b5%ec%a7%80%ec%82%ac%ed%95%ad/ | WordPress 리스트 (카테고리형) | N | 상단 페이지네이션, 본문 HTML `<div class="board-list">`. |
| `cls_notice` | 인문대학 | 국어국문학과/언어학과 통합 (리버럴스칼라스) | https://cls.snu.ac.kr/notice/ | WordPress standard | N | `li.post` 구조, 썸네일 포함 여부 확인 필요. |
| `sees_notice` | 자연과학대학 | 지구환경과학부(SEES) | https://sees.snu.ac.kr/community/notice | Custom (Bootstrap table) | N | `/community/notice` → AJAX 없이 HTML table, 페이지네이션 쿼리 `?page=`. |
| `stat_notice` | 자연과학대학 | 통계학과 | https://stat.snu.ac.kr/category/board-18-gn-969abdbt-20210204013659/ | WordPress category slug | N | 카테고리 slug 길음, 리스트/상세 동일 템플릿. |
| `cse_notice` | 공과대학 | 컴퓨터공학부 | https://cse.snu.ac.kr/community/notice | Drupal/Custom | N | `<div class="board_list">` table, `?page=` 기반 페이징. |
| `ece_admissions` | 공과대학 | 전기·컴퓨터공학부 (입시) | https://ece.snu.ac.kr/community/admissions | Custom board | N | 동일 도메인 내 `admissions`, `academics` 구조 같음, 날짜/조회수 column. |
| `ece_academics` | 공과대학 | 전기·컴퓨터공학부 (학사) | https://ece.snu.ac.kr/community/academics | Custom board | N | 상동, 카테고리만 변경. |
| `nursing_notice` | 간호대학 | 간호대학 행정실 | https://nursing.snu.ac.kr/board/notice | WordPress (board plugin) | N | `board?mode=list` 형태, detail는 `/board/notice?uid=` 패턴. |
| `art_painting` | 미술대학 | 서양화과 | https://art.snu.ac.kr/category/painting/?catemenu=Notice&type=major | WordPress + query params | N | 카테고리+쿼리 조합, `<article>` 리스트. |
| `learning_notice` | 교육학습개발센터 | 학습지원 | https://learning.snu.ac.kr/category/board-145-GN-5rT2jEg7-20230719130936/#none | WordPress category slug | N | 카테고리 ID 포함된 slug, AJAX 없이 정적 HTML. |
| `medicine_notice` | 의과대학 | 의대 행정실 | https://medicine.snu.ac.kr/fnt/nac/selectNoticeList.do?bbsId=BBSMSTR_000000000001 | JSP + q=JSON API | N | 리스트는 HTML table, JSON API `selectNoticeList.do` 지원, POST payload 필요. |
| `music_notice` | 음악대학 | 음악대학 행정실 | https://music.snu.ac.kr/notice | WordPress standard | N | `<section class="board-list">`, 첨부 아이콘 포함. |
| `gsds_notice` | 데이터사이언스대학원 | GSDS 공지 | https://gsds.snu.ac.kr/news/announcement/ | WordPress (custom theme) | N | `/news/announcement/` 리스트, detail은 `/news/announcement/{id}`. |
| `gsep_notice` | 지속가능과학기술대학원 | 공지사항 | https://gsep.snu.ac.kr/boards/notice/news/notice/ | Custom (Vue) | N | CSR 요소 있으나 HTML fallback 존재, `/boards/notice/news/notice/?page=`. |
| `gses_notice` | 농업생명과학대학 대학원 | 공지사항 | https://gses.snu.ac.kr/news/notice/notice?sc=y | Custom board | N | 쿼리 파라미터 `?pageIndex=` 사용, 테이블형. |
| `gspa_notice` | 행정대학원 | 공지사항 | https://gspa.snu.ac.kr/kr/Board/List/Notice | ASP.NET MVC | N | 리스트 AJAX 없음, detail은 `/Board/Read/Notice/{id}`. |
| `ist_notice` | 수리과학부 | 수리과학부 게시판 | https://ist.snu.ac.kr/category/board-186-gn-tnqrnsi7-20230904142222/ | WordPress category slug | N | slug 구조만 다름, 기존 WordPress 어댑터 재사용 가능. |
| `oia_notice` | 국제협력본부 | 전체 공지 | https://oia.snu.ac.kr/notice-all | Next.js/WordPress headless | N | 서버 렌더링되는 카드 리스트, detail 링크 `/notice/{slug}`. |
| `snu_general_notice` | 본부 | 중앙 공지 | https://www.snu.ac.kr/snunow/notice/genernal | Drupal-like | N | 중앙 포털 공지, 카테고리/검색 필터 포함. |

## Usage Notes
- `Format Hint`는 향후 어댑터 매칭에 활용할 키워드입니다. 실제 구현 시 DOM 구조를 캡처해 adapter별 셀렉터를 설정하세요.
- `medicine_notice`는 서버 측 JSP이지만 `bbsId` 파라미터로 JSON 응답을 주는 API가 존재합니다. 추후 HTTP POST 페이로드 캡처 필요.
- 모든 URL은 인증 없이 접근 가능한 공개 페이지로 확인했습니다. 이후 로그인 필요 게시판은 별도 섹션으로 분리하세요.
- 카탈로그는 임시 수집본입니다. 실제 운영 시 DB 컬렉션(`board_catalog`)을 만들어 `college`, `department`, `board_type`, `url`, `template_key`, `requires_auth`, `last_checked_at` 등을 저장할 계획입니다.
