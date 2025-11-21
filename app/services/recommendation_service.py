from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

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

        # fallback의 경우도 명세서 형식에 맞게 meta 수정
        fallback = await self.feed_service.get_feed(
            category=None,
            page=1,
            page_size=limit,
        )
        # fallback은 이미 올바른 형식이므로 그대로 반환
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
        combined_text = " ".join(filter(None, [(post.summary or post.body) for post in liked_posts])).strip()
        vector = await self._user_vector(liked_posts, combined_text)
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
                "total": len(items),
                "page": 1,
                "page_size": limit,
                "total_pages": 1,
            },
        }

    async def _user_vector(self, liked_posts: List[Post], combined_text: str) -> Optional[List[float]]:
        """
        Build a user preference vector.
        - Few likes: re-embed the combined text to capture shared context.
        - Many likes: prefer averaging stored post vectors to save LLM calls.
        - Fallback: if averaging fails, attempt a fresh embed.
        """
        like_count = len(liked_posts)
        # For small samples, re-embed text (higher fidelity, small cost).
        if like_count <= 5 and combined_text:
            vector = await self.llm_service.embed(combined_text)
            if vector:
                return self._l2_normalize(vector)

        # Try averaging stored vectors from Qdrant.
        post_ids = [str(post.id) for post in liked_posts]
        stored = await vector_store.fetch_vectors_by_post_ids(post_ids)
        averaged = self._mean_vector(stored.values())
        if averaged:
            return averaged

        # Fallback to text embedding if averaging failed.
        if combined_text:
            vector = await self.llm_service.embed(combined_text)
            if vector:
                return self._l2_normalize(vector)
        return None

    def _mean_vector(self, vectors: Iterable[List[float]]) -> Optional[List[float]]:
        vectors = [vec for vec in vectors if vec]
        if not vectors:
            return None

        length = len(vectors[0])
        summed = [0.0] * length
        used = 0
        for vec in vectors:
            # Skip vectors with mismatched dimensions
            if len(vec) != length:
                continue
            for i, value in enumerate(vec):
                summed[i] += value
            used += 1
        if used == 0:
            return None
        averaged = [value / used for value in summed]
        return self._l2_normalize(averaged)

    def _l2_normalize(self, vector: List[float]) -> List[float]:
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]

    async def _posts_from_hits(
        self,
        hits: List[Dict[str, Any]],
        exclude_ids: set[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        def _extract_post_id(hit: Dict[str, Any]) -> Optional[str]:
            return hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")

        # semantic score 순서 유지 (hits는 이미 점수 순으로 정렬되어 있음)
        ordered_ids = [
            ObjectId(post_id)
            for post_id in (_extract_post_id(hit) for hit in hits)
            if post_id and ObjectId.is_valid(post_id) and post_id not in exclude_ids
        ]
        if not ordered_ids:
            return []

        posts = await Post.find(In(Post.id, ordered_ids)).to_list()
        post_map = {str(post.id): post for post in posts}

        # hits 순서대로 포스트를 가져와서 _format_post_item 사용
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
            # _format_post_item 사용하여 일관된 형식으로 변환
            formatted_item = self.feed_service._format_post_item(post)
            # 디버깅을 위해 semantic score 추가
            formatted_item["semantic_score"] = hit.get("score")
            items.append(formatted_item)
            if len(items) >= limit:
                break
        return items
