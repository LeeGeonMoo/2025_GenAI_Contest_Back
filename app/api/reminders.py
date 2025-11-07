from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.services.reminder_service import ReminderService

router = APIRouter()
service = ReminderService()


class ReminderCreate(BaseModel):
    user_id: str
    post_id: str
    notify_at: datetime
    channel: str

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        allowed = {"email", "kakao"}
        if value not in allowed:
            raise ValueError(f"channel must be one of {allowed}")
        return value


@router.post("", summary="Create reminder")
async def create_reminder(payload: ReminderCreate):
    try:
        reminder = await service.create_reminder(
            user_id=payload.user_id,
            post_id=payload.post_id,
            notify_at=payload.notify_at,
            channel=payload.channel,
        )
        return reminder
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", summary="List reminders for a user")
async def list_reminders(
    user_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await service.list_reminders(user_id=user_id, page=page, page_size=page_size)
