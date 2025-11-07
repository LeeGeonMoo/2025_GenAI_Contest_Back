from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.search_service import SearchService

router = APIRouter()
service = SearchService()


@router.get("", summary="Hybrid keyword/semantic search (semantic stub)")
async def search(
    q: str = Query(..., min_length=1),
    mode: str = Query("keyword", pattern="^(keyword|semantic)$"),
    department: str | None = Query(default=None),
    grade: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    return await service.search(
        query=q,
        mode=mode,
        department=department,
        grade=grade,
        page=page,
        page_size=page_size,
    )
