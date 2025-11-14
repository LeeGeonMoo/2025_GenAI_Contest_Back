import pytest

from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_guardrail_weather_question():
    service = ChatService()
    response = await service.answer("오늘 날씨 어때?", user_id=None, department=None, grade=None)
    assert response["meta"]["refused"] is True
    assert response["meta"]["reason"] == "out_of_scope"
    assert response["notices"] == []
    assert (
        response["answer"]
        == service._refusal_message_for_reason("out_of_scope", "오늘 날씨 어때?")
    )


@pytest.mark.asyncio
async def test_chat_refuses_when_no_context(monkeypatch):
    service = ChatService()

    async def fake_contexts(self, question, department=None, grade=None):
        return []

    monkeypatch.setattr(ChatService, "_retrieve_contexts", fake_contexts)
    response = await service.answer("장학금 일정 알려줘", None, None, None)
    assert response["meta"]["reason"] == "no_context"
    assert (
        response["answer"]
        == service._refusal_message_for_reason("no_context", "장학금 일정 알려줘")
    )
    assert response["notices"] == []


@pytest.mark.asyncio
async def test_chat_success_with_stubbed_llm(monkeypatch):
    service = ChatService()
    context = [
        {
            "post_id": "507f1f77bcf86cd799439011",
            "title": "장학금 신청 안내",
            "summary": "2025-1학기 장학금 신청 일정입니다.",
            "body_snippet": "3월 1일까지 온라인으로 신청하세요.",
            "department": "컴퓨터공학부",
            "audience_grade": ["3"],
            "category": "장학",
            "source": "dummy",
            "posted_at": "2025-02-01T09:00:00",
            "deadline_at": "2025-03-01T23:59:00",
            "score": 0.9,
            "signals": {"semantic_score": 0.9, "keyword_rank": 0},
        }
    ]

    async def fake_contexts(self, question, department=None, grade=None):
        return context

    async def fake_grounded(self, question, contexts):
        return {
            "answer": "3월 1일까지 장학금 신청서를 제출하세요.",
            "citations": [contexts[0]["post_id"]],
            "source": "llm",
        }

    async def fake_verify(*args, **kwargs):
        return True, "ok"

    monkeypatch.setattr(ChatService, "_retrieve_contexts", fake_contexts)
    monkeypatch.setattr(ChatService, "_generate_grounded_answer", fake_grounded)
    monkeypatch.setattr(ChatService, "_verify_answer", fake_verify)

    response = await service.answer("장학금 언제 신청하나요?", "user-1", "컴퓨터공학부", "3")

    assert response["answer"].startswith("3월")
    assert response["citations"] == [context[0]["post_id"]]
    assert response["meta"]["refused"] is False
    assert response["meta"]["source"] == "llm"


@pytest.mark.asyncio
async def test_chat_verification_failure(monkeypatch):
    service = ChatService()
    context = [
        {
            "post_id": "507f1f77bcf86cd799439011",
            "title": "이벤트 안내",
            "summary": "요약",
            "body_snippet": "본문",
            "department": None,
            "audience_grade": [],
            "category": None,
            "source": "dummy",
            "posted_at": "2025-02-01T09:00:00",
            "deadline_at": None,
            "score": 0.9,
            "signals": {},
        }
    ]

    async def fake_contexts(self, question, department=None, grade=None):
        return context

    async def fake_grounded(self, question, contexts):
        return {
            "answer": "임시 답변",
            "citations": [contexts[0]["post_id"]],
            "source": "llm",
        }

    async def fake_verify(*args, **kwargs):
        return False, "bad"

    monkeypatch.setattr(ChatService, "_retrieve_contexts", fake_contexts)
    monkeypatch.setattr(ChatService, "_generate_grounded_answer", fake_grounded)
    monkeypatch.setattr(ChatService, "_verify_answer", fake_verify)

    response = await service.answer("행사 알려줘", None, None, None)
    assert response["meta"]["refused"] is True
    assert response["meta"]["reason"] == "verification_failed"
    assert response["notices"] == []
    assert (
        response["answer"]
        == service._refusal_message_for_reason("verification_failed", "행사 알려줘")
    )
