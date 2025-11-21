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

        ids = [pid for pid in user.liked_post_ids if pid]
        offset = max(page - 1, 0) * page_size
        paged_ids = ids[offset : offset + page_size]
        
        # 문자열 ID를 ObjectId로 변환하여 조회
        valid_object_ids = []
        for pid in paged_ids:
            try:
                if ObjectId.is_valid(pid):
                    valid_object_ids.append(ObjectId(pid))
            except (TypeError, ValueError):
                continue
        
        if not valid_object_ids:
            return {
                "items": [],
                "meta": {
                    "total": len(ids),
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (len(ids) + page_size - 1) // page_size if len(ids) > 0 else 0,
                },
            }
        
        # Beanie의 In 연산자 사용 (ObjectId 리스트 지원)
        # 다른 서비스들(search_service, recommendation_service)과 동일한 패턴 사용
        posts = await Post.find(In(Post.id, valid_object_ids)).to_list()
        
        # Preserve the order based on liked_post_ids slice
        # post_map의 키는 문자열로 변환된 post.id (paged_ids와 매칭하기 위해)
        post_map = {str(post.id): post for post in posts}
        
        # paged_ids는 문자열 리스트이므로, post_map의 키(문자열)와 매칭됨
        # liked_post_ids에 저장된 순서대로 items 생성
        items = [
            self.feed_service._format_post_item(post_map[pid])
            for pid in paged_ids
            if pid in post_map
        ]
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
