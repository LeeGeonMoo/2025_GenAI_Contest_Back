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
        """Post 모델을 API 응답 형식으로 변환"""
        # source를 객체 배열로 변환
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
