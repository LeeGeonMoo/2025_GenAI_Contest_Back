from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.interaction_service import InteractionService

router = APIRouter()
service = InteractionService()


class LikeRequest(BaseModel):
    user_id: str
    post_id: str


@router.post("", summary="Like a post")
async def like_post(payload: LikeRequest):
    try:
        return await service.like_post(payload.user_id, payload.post_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{user_id}/{post_id}", summary="Remove like from a post")
async def unlike_post(user_id: str, post_id: str):
    try:
        return await service.unlike_post(user_id, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
