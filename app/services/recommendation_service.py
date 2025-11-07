from __future__ import annotations

from typing import Any, Dict, List, Optional

from beanie.operators import In
from bson import ObjectId

from app.models.post import Post
from app.models.user import User
from app.services import vector_store
from app.services.feed_service import FeedService
from app.services.llm_service import LLMService


class RecommendationService:
    """
    Provides profile-based feed plus semantic similarity recommendations using
    user likes. Falls back to baseline feed when insufficient data is present.
    """

    def __init__(
        self,
        feed_service: FeedService | None = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self.feed_service = feed_service or FeedService()
        self.llm_service = llm_service or LLMService()

    async def profile_recommendations(
        self,
        department: Optional[str],
        grade: Optional[str],
        limit: int,
    ) -> Dict[str, Any]:
        feed = await self.feed_service.get_feed(
            department=department,
            grade=grade,
            page=1,
            page_size=limit,
        )
        feed["meta"]["mode"] = "profile"
        feed["meta"]["limit"] = limit
        return feed

    async def like_recommendations(
        self,
        user_id: Optional[str],
        limit: int,
    ) -> Dict[str, Any]:
        semantic = await self._semantic_from_likes(user_id, limit)
        if semantic:
            return semantic

        fallback = await self.feed_service.get_feed(
            department=None,
            grade=None,
            page=1,
            page_size=limit,
        )
        fallback["meta"]["mode"] = "likes-fallback"
        fallback["meta"]["limit"] = limit
        fallback["meta"]["user_id"] = user_id
        return fallback

    async def _semantic_from_likes(
        self,
        user_id: Optional[str],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None

        user = await User.get(user_id)
        if not user or not user.liked_post_ids:
            return None

        object_ids = [
            ObjectId(post_id)
            for post_id in user.liked_post_ids[-5:]
            if ObjectId.is_valid(post_id)
        ]
        if not object_ids:
            return None

        liked_posts = await Post.find(In(Post.id, object_ids)).to_list()
        combined_text = " ".join(
            filter(None, [(post.summary or post.body) for post in liked_posts])
        ).strip()
        if not combined_text:
            return None

        vector = await self.llm_service.embed(combined_text)
        if not vector:
            return None

        hits = await vector_store.search_similar(vector, limit=limit * 2)
        exclude_ids = {str(post.id) for post in liked_posts}
        items = await self._posts_from_hits(hits, exclude_ids, limit)
        if not items:
            return None

        return {
            "items": items,
            "meta": {
                "mode": "likes-semantic",
                "limit": limit,
                "user_id": user_id,
                "source_likes": len(liked_posts),
            },
        }

    async def _posts_from_hits(
        self,
        hits: List[Dict[str, Any]],
        exclude_ids: set[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        def _extract_post_id(hit: Dict[str, Any]) -> Optional[str]:
            return hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")

        ordered_ids = [
            ObjectId(post_id)
            for post_id in (_extract_post_id(hit) for hit in hits)
            if post_id and ObjectId.is_valid(post_id) and post_id not in exclude_ids
        ]
        if not ordered_ids:
            return []

        posts = await Post.find(In(Post.id, ordered_ids)).to_list()
        post_map = {str(post.id): post for post in posts}

        items: List[Dict[str, Any]] = []
        for hit in hits:
            post_id = _extract_post_id(hit)
            if not post_id:
                continue
            if post_id in exclude_ids:
                continue
            post = post_map.get(post_id)
            if not post:
                continue
            data = post.model_dump()
            data["semantic_score"] = hit.get("score")
            items.append(data)
            if len(items) >= limit:
                break
        return items
