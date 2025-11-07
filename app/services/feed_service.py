from __future__ import annotations

from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId

from app.models.post import Post


class FeedService:
    """
    Provides simple feed and post retrieval backed by MongoDB.
    """

    async def get_feed(
        self,
        department: Optional[str],
        grade: Optional[str],
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if department:
            filters["department"] = department
        if grade:
            filters["audience_grade"] = grade
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

        scored = [self._score_post(post, department, grade) for post in posts]

        return {
            "items": scored,
            "meta": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "scoring_weights": {
                    "department": 0.4,
                    "grade": 0.2,
                    "deadline": 0.2,
                    "recency": 0.2,
                },
            },
        }

    async def get_post(self, post_id: str | PydanticObjectId) -> Optional[Post]:
        return await Post.get(post_id)

    def _score_post(
        self,
        post: Post,
        department: Optional[str],
        grade: Optional[str],
    ) -> Dict[str, Any]:
        weight_department = 0.4
        weight_grade = 0.2
        weight_deadline = 0.2
        weight_recency = 0.2

        dept_match = 1.0 if department and post.department == department else 0.5
        grade_match = (
            1.0 if grade and post.audience_grade and grade in post.audience_grade else 0.5
        )
        deadline_boost = self._deadline_boost(post)
        recency_boost = self._recency_boost(post)

        score = (
            weight_department * dept_match
            + weight_grade * grade_match
            + weight_deadline * deadline_boost
            + weight_recency * recency_boost
        )

        return {
            **post.model_dump(),
            "score": score,
            "rank_reason": {
                "dept_match": dept_match,
                "grade_match": grade_match,
                "deadline_boost": deadline_boost,
                "recency_boost": recency_boost,
            },
        }

    def _deadline_boost(self, post: Post) -> float:
        if not post.deadline_at:
            return 0.5
        delta = (post.deadline_at - post.posted_at).total_seconds() / 3600
        if delta <= 0:
            return 0.0
        return min(1.0, 1 / (delta / 24))

    def _recency_boost(self, post: Post) -> float:
        hours_since_post = (post.created_at - post.posted_at).total_seconds() / 3600
        if hours_since_post <= 0:
            return 1.0
        return max(0.1, 1 / (1 + hours_since_post / 24))
