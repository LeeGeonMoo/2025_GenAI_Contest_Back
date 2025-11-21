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
    
    # _format_post_item에 없는 추가 정보만 포함
    formatted["summary"] = post.summary
    formatted["college"] = post.college
    formatted["department"] = post.department  # source에 name으로만 있으므로 별도로도 제공
    formatted["audience_grade"] = post.audience_grade or []
    formatted["url"] = post.url  # source에 url로만 있으므로 별도로도 제공
    formatted["likes"] = post.likes
    
    return formatted
