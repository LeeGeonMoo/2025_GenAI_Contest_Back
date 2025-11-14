# 백엔드 변경 사항 정리

## 개요

프론트엔드 API 명세서에 맞춰 백엔드 API를 수정한 변경 사항을 정리합니다.

**변경 일자**: 2024년 (프론트엔드 API 명세서 기준)

---

## 1. GET /feed API 수정

### 1.1 Query Parameters 변경

**변경 전:**
```python
async def get_feed(
    department: str | None = Query(default=None),
    grade: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
```

**변경 후:**
```python
async def get_feed(
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
```

**변경 내용:**
- ❌ `department` 파라미터 제거
- ❌ `grade` 파라미터 제거
- ✅ `category` 파라미터 추가 (카테고리 필터링용)

**파일**: `app/api/feed.py`

---

### 1.2 FeedService.get_feed() 메서드 수정

**변경 전:**
- `department`, `grade` 파라미터로 필터링
- 응답에 `score`, `rank_reason`, `scoring_weights` 포함

**변경 후:**
- `category` 파라미터로 필터링
- 응답 구조를 프론트엔드 명세서에 맞게 변환
- `_format_post_item()` 메서드로 데이터 변환

**주요 변경 사항:**

1. **필터링 로직 변경**
   ```python
   # 변경 전
   if department:
       filters["department"] = department
   if grade:
       filters["audience_grade"] = grade
   
   # 변경 후
   if category:
       filters["category"] = category
   ```

2. **응답 구조 변경**
   ```python
   # 변경 전
   scored = [self._score_post(post, department, grade) for post in posts]
   return {
       "items": scored,
       "meta": {
           "total": total,
           "page": page,
           "page_size": page_size,
           "scoring_weights": {...},
       },
   }
   
   # 변경 후
   items = [self._format_post_item(post) for post in posts]
   total_pages = (total + page_size - 1) // page_size if total > 0 else 0
   return {
       "items": items,
       "meta": {
           "total": total,
           "page": page,
           "page_size": page_size,
           "total_pages": total_pages,
       },
   }
   ```

3. **새로운 메서드 추가: `_format_post_item()`**
   ```python
   def _format_post_item(self, post: Post) -> Dict[str, Any]:
       """Post 모델을 API 응답 형식으로 변환"""
       source_list = []
       if post.source:
           source_list.append({"name": post.source, "url": None})
       
       return {
           "id": str(post.id),
           "title": post.title,
           "tags": post.tags,
           "category": post.category or "",
           "source": source_list,
           "posted_at": post.posted_at.isoformat() if post.posted_at else None,
           "deadline": post.deadline_at.isoformat() if post.deadline_at else None,
       }
   ```

4. **제거된 메서드**
   - `_score_post()` - 점수 계산 로직 제거
   - `_deadline_boost()` - 마감일 부스트 계산 제거
   - `_recency_boost()` - 최신성 부스트 계산 제거

**파일**: `app/services/feed_service.py`

---

### 1.3 응답 구조 변경

**변경 전 응답:**
```json
{
  "items": [
    {
      "_id": "...",
      "title": "...",
      "department": "...",
      "audience_grade": [...],
      "source": "string",
      "posted_at": "...",
      "deadline_at": "...",
      "score": 0.95,
      "rank_reason": {...}
    }
  ],
  "meta": {
    "total": 100,
    "page": 1,
    "page_size": 20,
    "scoring_weights": {...}
  }
}
```

**변경 후 응답:**
```json
{
  "items": [
    {
      "id": "string",
      "title": "string",
      "tags": ["string"],
      "category": "string",
      "source": [
        {
          "name": "string",
          "url": null
        }
      ],
      "posted_at": "2024-01-01T00:00:00Z",
      "deadline": "2024-01-31T00:00:00Z | null"
    }
  ],
  "meta": {
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

**주요 변경점:**
- ✅ `_id` → `id` (문자열로 변환)
- ✅ `tags` 필드 추가 (배열)
- ✅ `source` 문자열 → 객체 배열 `[{"name": "...", "url": null}]`
- ✅ `deadline_at` → `deadline` (필드명 변경)
- ✅ `posted_at`, `deadline` ISO 8601 형식으로 변환
- ✅ `meta.total_pages` 추가
- ❌ `score`, `rank_reason`, `scoring_weights` 제거

---

## 2. CORS 설정 추가

### 2.1 변경 내용

프론트엔드(`http://localhost:5173`)에서 백엔드 API를 호출할 수 있도록 CORS 미들웨어를 추가했습니다.

**파일**: `app/main.py`

**추가된 코드:**
```python
from fastapi.middleware.cors import CORSMiddleware

# CORS 설정
application.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite 개발 서버
        "http://localhost:3000",  # React 개발 서버 (필요시)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**설정 내용:**
- 허용된 Origin: `http://localhost:5173`, `http://localhost:3000`
- 모든 HTTP 메서드 허용
- 모든 헤더 허용
- Credentials 허용

---

## 3. API 라우터 Prefix 추가

### 3.1 변경 내용

모든 API 엔드포인트에 `/api` prefix를 추가했습니다.

**파일**: `app/main.py`

**변경 전:**
```python
application.include_router(router)
```

**변경 후:**
```python
application.include_router(router, prefix="/api")
```

**영향받는 엔드포인트:**
- `/feed` → `/api/feed`
- `/feed/reco-user` → `/api/feed/reco-user`
- `/feed/reco-likes` → `/api/feed/reco-likes`
- `/posts/{post_id}` → `/api/posts/{post_id}`
- `/search` → `/api/search`
- `/likes` → `/api/likes`
- `/chat` → `/api/chat`
- 기타 모든 API 엔드포인트

**참고**: Root 경로(`/`)와 Health check(`/healthz`)도 `/api/`와 `/api/healthz`로 이동합니다.

---

## 4. 변경 사항 요약

### 4.1 수정된 파일

1. **`app/api/feed.py`**
   - Query parameters 변경 (`department`, `grade` → `category`)

2. **`app/services/feed_service.py`**
   - `get_feed()` 메서드 로직 변경
   - `_format_post_item()` 메서드 추가
   - `_score_post()`, `_deadline_boost()`, `_recency_boost()` 메서드 제거

3. **`app/main.py`**
   - CORS 미들웨어 추가
   - API 라우터에 `/api` prefix 추가

### 4.2 주요 변경 사항

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| Query Parameters | `department`, `grade` | `category` |
| Response 필드 | `score`, `rank_reason`, `scoring_weights` | `total_pages` |
| Source 형식 | 문자열 | 객체 배열 `[{"name": "...", "url": null}]` |
| Deadline 필드명 | `deadline_at` | `deadline` |
| ID 필드명 | `_id` | `id` (문자열) |
| CORS 설정 | 없음 | `http://localhost:5173` 허용 |
| API Prefix | 없음 | `/api` |

---

## 5. 호환성 및 마이그레이션

### 5.1 Breaking Changes

1. **Query Parameters 변경**
   - 기존 `department`, `grade` 파라미터 사용 시 오류 발생
   - `category` 파라미터로 변경 필요

2. **Response 구조 변경**
   - `score`, `rank_reason`, `scoring_weights` 필드 제거
   - `source` 필드 형식 변경 (문자열 → 객체 배열)
   - `deadline_at` → `deadline` 필드명 변경

3. **API 경로 변경**
   - 모든 API 엔드포인트에 `/api` prefix 추가
   - 기존 클라이언트 코드 수정 필요

### 5.2 테스트 영향

- `tests/test_feed_service.py`에서 제거된 메서드(`_score_post`, `_deadline_boost`)를 사용하는 테스트가 있을 경우 수정 필요

---

## 6. 다음 단계

### 6.1 구현 필요 항목

프론트엔드 API 명세서에 따르면 다음 API들이 아직 구현되지 않았습니다:

1. **GET /likes/{user_id}** - 사용자의 좋아요한 포스트 목록 조회
2. **GET /users/{user_id}** - 사용자 정보 조회
3. **PUT /users/{user_id}** - 사용자 프로필 수정
4. **GET /users/{user_id}/notifications** - 사용자 알림 설정 조회
5. **PUT /users/{user_id}/notifications** - 사용자 알림 설정 업데이트
6. **GET /search**에 `category` 파라미터 추가
7. **GET /search**에 `source` 파라미터 추가

### 6.2 개선 사항

- `source` 필드의 `url` 값을 실제 URL로 채우는 로직 추가 고려
- 카테고리 목록을 동적으로 가져오는 API 추가 고려

---

## 참고 자료

- 프론트엔드 API 명세서: `2025_GenAI_Contest_Front/docs/FRONTEND_API_SPEC.md`
- FastAPI CORS 문서: https://fastapi.tiangolo.com/tutorial/cors/

