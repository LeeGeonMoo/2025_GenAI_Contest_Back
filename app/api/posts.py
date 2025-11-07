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
    return post
