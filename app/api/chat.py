from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.chat_service import ChatService

router = APIRouter()
service = ChatService()


class ChatRequest(BaseModel):
    # 짧은 인사(예: "안녕")도 허용하기 위해 최소 길이를 1로 완화
    question: str = Field(..., min_length=1, max_length=400)
    user_id: str | None = None
    department: str | None = None
    grade: str | None = None
    session_id: str | None = None


@router.post("", summary="대화형 RAG 챗봇")
async def chat(payload: ChatRequest):
    try:
        return await service.answer(
            question=payload.question,
            user_id=payload.user_id,
            department=payload.department,
            grade=payload.grade,
            session_id=payload.session_id,
        )
    except Exception as exc:  # pragma: no cover - unexpected runtime error
        raise HTTPException(status_code=500, detail="chat_failure") from exc
