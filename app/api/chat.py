from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.chat_service import ChatService

router = APIRouter()
service = ChatService()


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=400)
    user_id: str | None = None
    department: str | None = None
    grade: str | None = None


@router.post("", summary="공지 기반 RAG 챗봇")
async def chat(payload: ChatRequest):
    try:
        return await service.answer(
            question=payload.question,
            user_id=payload.user_id,
            department=payload.department,
            grade=payload.grade,
        )
    except Exception as exc:  # pragma: no cover - unexpected runtime error
        raise HTTPException(status_code=500, detail="chat_failure") from exc
