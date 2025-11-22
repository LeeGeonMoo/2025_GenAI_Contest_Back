from __future__ import annotations

from typing import Any, Dict, List, Optional

from beanie.operators import In
from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field

from app.models.post import Post
from app.models.user import User
from app.services.feed_service import FeedService


class UserUpdate(BaseModel):
    name: Optional[str] = None
    college: Optional[str] = None
    department: Optional[str] = None
    grade: Optional[str] = None
    interests: Optional[List[str]] = Field(default=None)


class NotificationUpdate(BaseModel):
    recommend_email: Optional[bool] = None
    deadline_alert: Optional[bool] = None


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
        # updated_at 갱신
        from datetime import datetime
        user.updated_at = datetime.utcnow()
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
            return {
                "items": [],
                "meta": {
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                },
            }

        ids = []
        for pid in user.liked_post_ids:
            if not pid:
                continue
            try:
                if ObjectId.is_valid(pid):
                    ids.append(pid)
            except (TypeError, ValueError):
                continue
        if not ids:
            return {
                "items": [],
                "meta": {
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                },
            }

        skip = max(page - 1, 0) * page_size
        object_ids = [ObjectId(pid) for pid in ids]
        posts = await (
            Post.find(In(Post.id, object_ids))
            .sort(-Post.posted_at)
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        items = [self.feed_service._format_post_item(post) for post in posts]
        total = len(ids)
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

    async def get_notifications(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자의 알림 설정 조회"""
        user = await User.get(user_id)
        if not user:
            return None
        return {
            "recommend_email": user.recommend_email,
            "deadline_alert": user.deadline_alert,
        }

    async def update_notifications(
        self, user_id: str, payload: NotificationUpdate
    ) -> Optional[Dict[str, Any]]:
        """사용자의 알림 설정 업데이트"""
        user = await User.get(user_id)
        if not user:
            return None
        updates: Dict[str, Any] = payload.model_dump(exclude_none=True)
        for key, value in updates.items():
            setattr(user, key, value)
        # updated_at 갱신
        from datetime import datetime
        user.updated_at = datetime.utcnow()
        await user.save()
        return {
            "recommend_email": user.recommend_email,
            "deadline_alert": user.deadline_alert,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
