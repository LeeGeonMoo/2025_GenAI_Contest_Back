from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.conversation import Conversation, Message

router = APIRouter()


@router.get("/{session_id}/messages", summary="대화 세션 메시지 조회")
async def list_messages(
    session_id: str,
    limit: int = Query(10, ge=1, le=50),
):
    convo = await Conversation.get(session_id)
    if not convo:
        raise HTTPException(status_code=404, detail="session_not_found")
    messages = (
        await Message.find(Message.conversation_id == session_id)
        .sort(-Message.created_at)
        .limit(limit)
        .to_list()
    )
    messages.reverse()
    return {"items": messages, "meta": {"session_id": session_id, "count": len(messages)}}


@router.post("/{session_id}/reset", summary="대화 세션 초기화")
async def reset_session(session_id: str):
    convo = await Conversation.get(session_id)
    if not convo:
        raise HTTPException(status_code=404, detail="session_not_found")
    await Message.find(Message.conversation_id == session_id).delete()
    await convo.delete()
    return {"status": "reset", "session_id": session_id}
