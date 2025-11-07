import pytest

from app.core.config import get_settings
from app.services.llm_service import LLMService


@pytest.mark.asyncio
async def test_llm_summary_fallback_truncates():
    service = LLMService()
    text = "공지 본문 " * 50
    summary = await service.summarize(text)
    assert len(summary) <= 163
    assert summary.endswith("...")


@pytest.mark.asyncio
async def test_llm_embedding_fallback_size():
    service = LLMService()
    vector = await service.embed("테스트 임베딩")
    assert vector is not None
    assert len(vector) == get_settings().qdrant_vector_size
