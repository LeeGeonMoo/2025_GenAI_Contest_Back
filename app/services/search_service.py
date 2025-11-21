from __future__ import annotations

from typing import Any, Dict, List, Optional

from beanie.operators import In
from bson import ObjectId

from app.models.post import Post
from app.services.feed_service import FeedService
from app.services.llm_service import LLMService
from app.services import vector_store


class SearchService:
    """Hybrid keyword/semantic search with graceful fallback."""

    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self.llm_service = llm_service or LLMService()
        self.feed_service = FeedService()

    async def search(
        self,
        query: str,
        category: Optional[str],
        source: Optional[List[str]],
        mode: str,
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        offset = max(page - 1, 0) * page_size

        if mode == "semantic":
            semantic = await self._semantic_search(query, category, source, page_size, offset)
            if semantic:
                total_pages = (
                    (semantic["meta"]["total"] + page_size - 1) // page_size
                    if semantic["meta"]["total"] > 0
                    else 0
                )
                semantic["meta"].update(
                    {
                        "page": page,
                        "page_size": page_size,
                        "total_pages": total_pages,
                    }
                )
                return semantic

        keyword = await self._keyword_search(query, category, source, page, page_size)
        total_pages = (
            (keyword["meta"]["total"] + page_size - 1) // page_size
            if keyword["meta"]["total"] > 0
            else 0
        )
        keyword["meta"].update({"total_pages": total_pages})
        return keyword

    async def _semantic_search(
        self,
        query: str,
        category: Optional[str],
        source: Optional[List[str]],
        page_size: int,
        offset: int,
    ) -> Optional[Dict[str, Any]]:
        vector = await self.llm_service.embed(query)
        if not vector:
            return None

        hits = await vector_store.search_similar(vector, limit=page_size * 2, offset=0)
        if not hits:
            return None

        mongo_ids = [
            ObjectId(post_id)
            for post_id in (
                hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")
                for hit in hits
            )
            if post_id and ObjectId.is_valid(post_id)
        ]
        if not mongo_ids:
            return None

        posts = await Post.find(In(Post.id, mongo_ids)).to_list()
        post_map = {str(post.id): post for post in posts}

        # 필터링 적용
        filters = self._build_filters(category, source)
        filtered_posts = []
        for hit in hits:
            post_id = hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")
            post = post_map.get(post_id)
            if not post:
                continue
            # 필터 적용
            if filters and not self._matches_filters(post, filters):
                continue
            filtered_posts.append((post, hit["score"]))

        # 점수 순으로 정렬
        filtered_posts.sort(key=lambda x: x[1], reverse=True)

        # 페이지네이션 적용
        paged_posts = filtered_posts[offset : offset + page_size]

        # _format_post_item을 사용하여 일관된 형식으로 변환
        items = [self.feed_service._format_post_item(post) for post, _ in paged_posts]

        # 전체 개수 계산 (필터 적용 후)
        total = len(filtered_posts)

        return {
            "items": items,
            "meta": {
                "total": total,
            },
        }

    async def _keyword_search(
        self,
        query: str,
        category: Optional[str],
        source: Optional[List[str]],
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        filters = self._build_filters(category, source)
        if query:
            regex = {"$regex": query, "$options": "i"}
            filters["$or"] = [
                {"title": regex},
                {"summary": regex},
                {"body": regex},
            ]

        offset = max(page - 1, 0) * page_size

        cursor = Post.find(filters).skip(offset).limit(page_size)
        total = await Post.find(filters).count()
        items: List[Post] = await cursor.to_list()

        # _format_post_item을 사용하여 일관된 형식으로 변환
        formatted_items = [self.feed_service._format_post_item(item) for item in items]

        return {
            "items": formatted_items,
            "meta": {
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }

    def _build_filters(
        self,
        category: Optional[str],
        source: Optional[List[str]],
    ) -> Dict[str, Any]:
        """필터 조건을 MongoDB 쿼리 형식으로 변환"""
        filters: Dict[str, Any] = {}
        if category:
            filters["category"] = category
        if source and len(source) > 0:
            # source는 department 필드로 필터링
            filters["department"] = {"$in": source}
        return filters

    def _matches_filters(self, post: Post, filters: Dict[str, Any]) -> bool:
        """Post 객체가 필터 조건을 만족하는지 확인 (시맨틱 검색용)"""
        if "category" in filters and post.category != filters["category"]:
            return False
        if "department" in filters:
            dept_filter = filters["department"]
            if isinstance(dept_filter, dict) and "$in" in dept_filter:
                # source 필터 (다중 선택)
                if post.department not in dept_filter["$in"]:
                    return False
            elif post.department != dept_filter:
                return False
        return True
