from __future__ import annotations

from typing import Any, Dict, List, Optional

from beanie.operators import In
from pydantic import BaseModel, EmailStr, Field

from app.models.post import Post
from app.models.user import User
from app.services.feed_service import FeedService


class UserUpdate(BaseModel):
    college: Optional[str] = None
    department: Optional[str] = None
    grade: Optional[str] = None
    interests: Optional[List[str]] = Field(default=None)


class UserService:
    def __init__(self) -> None:
        self.feed_service = FeedService()

    async def get_user(self, user_id: str) -> Optional[User]:
        return await User.get(user_id)

    async def update_user(self, user_id: str, payload: UserUpdate) -> Optional[User]:
        user = await User.get(user_id)
        if not user:
            return None
        updates: Dict[str, Any] = payload.model_dump(exclude_none=True)
        for key, value in updates.items():
            setattr(user, key, value)
        await user.save()
        return user

    async def list_likes(
        self,
        user_id: str,
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        user = await User.get(user_id)
        if not user or not user.liked_post_ids:
            return {"items": [], "meta": {"total": 0, "page": page, "page_size": page_size}}

        ids = [pid for pid in user.liked_post_ids if pid]
        offset = max(page - 1, 0) * page_size
        paged_ids = ids[offset : offset + page_size]
        posts = await Post.find(In(Post.id, paged_ids)).to_list()
        # Preserve the order based on liked_post_ids slice
        post_map = {str(post.id): post for post in posts}
        items = [
            self.feed_service._format_post_item(post_map[pid])
            for pid in paged_ids
            if pid in post_map
        ]
        return {
            "items": items,
            "meta": {"total": len(ids), "page": page, "page_size": page_size},
        }
