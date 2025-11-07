from fastapi import APIRouter

from app.api import feed, posts, search, likes, reminders
from app.core.config import get_settings

router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict:
    settings = get_settings()
    return {
        "service": settings.project_name,
        "environment": settings.environment,
        "message": "Intelligent campus notice platform backend is running.",
    }


@router.get("/healthz", tags=["health"])
async def healthz() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.project_name,
        "timezone": settings.timezone,
    }


router.include_router(feed.router, prefix="/feed", tags=["feed"])
router.include_router(posts.router, prefix="/posts", tags=["posts"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(likes.router, prefix="/likes", tags=["interactions"])
router.include_router(reminders.router, prefix="/reminders", tags=["reminders"])
