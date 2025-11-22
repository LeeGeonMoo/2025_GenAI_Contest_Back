from __future__ import annotations

from fastapi import APIRouter, Query

from app.models.user import User
from app.services.feed_service import FeedService
from app.services.recommendation_service import RecommendationService

router = APIRouter()
feed_service = FeedService()
reco_service = RecommendationService(feed_service)


@router.get("", summary="Get baseline feed")
async def get_feed(
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    exclude_user_id: str | None = Query(default=None),
):
    exclude_ids = None
    if exclude_user_id:
        user = await User.get(exclude_user_id)
        if user and user.liked_post_ids:
            exclude_ids = {pid for pid in user.liked_post_ids if pid}
    return await feed_service.get_feed(
        category=category,
        page=page,
        page_size=page_size,
        exclude_ids=exclude_ids,
    )


@router.get("/reco-user", summary="User profile based recommendation")
async def reco_user(
    user_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
):
    return await reco_service.profile_recommendations(
        user_id=user_id,
        limit=limit,
    )


@router.get("/reco-likes", summary="Like-based semantic recommendation")
async def reco_likes(
    user_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
):
    return await reco_service.like_recommendations(
        user_id=user_id,
        limit=limit,
    )
