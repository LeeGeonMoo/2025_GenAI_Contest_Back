from __future__ import annotations

from typing import Any, Dict, List, Optional

from beanie.operators import In
from bson import ObjectId

from app.models.post import Post
from app.services.llm_service import LLMService
from app.services import vector_store


class SearchService:
    """Hybrid keyword/semantic search with graceful fallback."""

    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self.llm_service = llm_service or LLMService()

    async def search(
        self,
        query: str,
        mode: str,
        department: Optional[str],
        grade: Optional[str],
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        offset = max(page - 1, 0) * page_size

        if mode == "semantic":
            semantic = await self._semantic_search(query, department, grade, page_size, offset)
            if semantic:
                semantic["meta"].update({"page": page, "page_size": page_size, "mode": "semantic"})
                return semantic

        keyword = await self._keyword_search(query, department, grade, page, page_size)
        keyword["meta"].update({"mode": "keyword" if mode == "keyword" else "fallback"})
        return keyword

    async def _semantic_search(
        self,
        query: str,
        department: Optional[str],
        grade: Optional[str],
        page_size: int,
        offset: int,
    ) -> Optional[Dict[str, Any]]:
        vector = await self.llm_service.embed(query)
        if not vector:
            return None

        hits = await vector_store.search_similar(vector, limit=page_size, offset=offset)
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

        items = []
        for hit in hits:
            post_id = hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")
            post = post_map.get(post_id)
            if not post:
                continue
            data = post.model_dump()
            data["semantic_score"] = hit["score"]
            items.append(data)

        filters = self._build_filters(department, grade)
        total = await Post.find(filters).count()

        return {
            "items": items,
            "meta": {
                "total": total,
            },
        }

    async def _keyword_search(
        self,
        query: str,
        department: Optional[str],
        grade: Optional[str],
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        filters = self._build_filters(department, grade)
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

        return {
            "items": [item.model_dump() for item in items],
            "meta": {
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }

    def _build_filters(
        self,
        department: Optional[str],
        grade: Optional[str],
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if department:
            filters["department"] = department
        if grade:
            filters["audience_grade"] = grade
        return filters
