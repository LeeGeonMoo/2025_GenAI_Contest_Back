from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.search_service import SearchService

router = APIRouter()
service = SearchService()


@router.get("", summary="Hybrid keyword/semantic search")
async def search(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    mode: str = Query("keyword", pattern="^(keyword|semantic)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    return await service.search(
        query=q,
        category=category,
        source=source,
        mode=mode,
        page=page,
        page_size=page_size,
    )
