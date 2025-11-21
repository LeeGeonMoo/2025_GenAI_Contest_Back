from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.feed_service import FeedService

router = APIRouter()
service = FeedService()


@router.get("/{post_id}", summary="Fetch a single post by id")
async def get_post(post_id: str):
    post = await service.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # _format_post_item을 사용하여 일관된 형식으로 변환 (body 필드 제외)
    formatted = service._format_post_item(post)
    # _id를 id로 변환
    formatted["id"] = str(post.id)
    return formatted
