from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.user_service import (
    NotificationUpdate,
    UserService,
    UserUpdate,
)

router = APIRouter()
service = UserService()


@router.get("/{user_id}", summary="사용자 프로필 조회")
async def get_user(user_id: str):
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # 프론트엔드 명세서에 맞게 응답 형식 변환
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "college": user.college,
        "department": user.department,
        "grade": user.grade,
        "interests": user.interests or [],
    }


@router.put("/{user_id}", summary="사용자 프로필 수정")
async def update_user(user_id: str, payload: UserUpdate):
    user = await service.update_user(user_id, payload)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # 프론트엔드 명세서에 맞게 응답 형식 변환
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "college": user.college,
        "department": user.department,
        "grade": user.grade,
        "interests": user.interests or [],
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get("/{user_id}/likes", summary="사용자 좋아요 목록")
async def list_likes(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await service.list_likes(user_id=user_id, page=page, page_size=page_size)


@router.get("/{user_id}/notifications", summary="사용자 알림 설정 조회")
async def get_notifications(user_id: str):
    notifications = await service.get_notifications(user_id)
    if notifications is None:
        raise HTTPException(status_code=404, detail="User not found")
    return notifications


@router.put("/{user_id}/notifications", summary="사용자 알림 설정 업데이트")
async def update_notifications(user_id: str, payload: NotificationUpdate):
    notifications = await service.update_notifications(user_id, payload)
    if notifications is None:
        raise HTTPException(status_code=404, detail="User not found")
    return notifications
