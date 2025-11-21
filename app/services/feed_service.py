from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId

from app.models.post import Post


class FeedService:
    """
    Provides simple feed and post retrieval backed by MongoDB.
    """

    async def get_feed(
        self,
        category: Optional[str],
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if category:
            filters["category"] = category
        exclude_sources = {
            None,
            "",
            "seed_posts",
            "dummy-source",
            "scholarship-board",
            "internship-board",
            "scholarship-source",
            "internship-source",
        }
        filters["source"] = {"$nin": list(exclude_sources)}

        offset = max(page - 1, 0) * page_size

        total = await Post.find(filters).count()
        posts: List[Post] = (
            await Post.find(filters)
            .sort(-Post.posted_at)
            .skip(offset)
            .limit(page_size)
            .to_list()
        )

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

    async def get_post(self, post_id: str | PydanticObjectId) -> Optional[Post]:
        return await Post.get(post_id)

    def _format_post_item(self, post: Post) -> Dict[str, Any]:
        """Post 객체를 API 응답 포맷으로 변환"""
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

    # --------- Scoring helpers (retained for compatibility with tests) ---------
    def _score_post(
        self,
        post: Post,
        department: Optional[str],
        grade: Optional[str],
    ) -> Dict[str, Any]:
        dept_match = 1.0 if department and post.department == department else 0.0
        grade_match = 1.0 if grade and grade in (post.audience_grade or []) else 0.0

        deadline_boost = self._deadline_boost(post)
        recency_boost = self._recency_boost(post)

        score = (
            0.4 * dept_match
            + 0.2 * grade_match
            + 0.2 * deadline_boost
            + 0.2 * recency_boost
        )
        return {
            "id": str(post.id),
            "title": post.title,
            "score": round(score, 4),
            "rank_reason": {
                "dept_match": dept_match,
                "grade_match": grade_match,
                "deadline_boost": deadline_boost,
                "recency_boost": recency_boost,
            },
        }

    def _deadline_boost(self, post: Post) -> float:
        if not post.deadline_at or not post.posted_at:
            return 0.5
        delta_days = (post.deadline_at - post.posted_at).total_seconds() / 86400
        if delta_days <= 0:
            return 0.1
        return max(0.1, 1 / (1 + delta_days))

    def _recency_boost(self, post: Post) -> float:
        if not post.posted_at:
            return 0.3
        now = datetime.now(timezone.utc)
        posted_at = post.posted_at
        # Naive datetime은 UTC 기준으로 간주
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        delta_hours = (now - posted_at).total_seconds() / 3600
        if delta_hours < 0:
            delta_hours = 0
        return max(0.1, 1 / (1 + delta_hours / 24))
