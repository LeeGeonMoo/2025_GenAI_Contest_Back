import pytest

from app.core.config import get_settings
from app.services.llm_service import LLMService


@pytest.mark.asyncio
async def test_llm_summary_fallback_truncates():
    service = LLMService()
    service.client.summary_enabled = False
    text = "공지 본문 " * 50
    summary = await service.summarize(text)
    assert len(summary) <= 163
    assert summary.endswith("...")


@pytest.mark.asyncio
async def test_llm_embedding_fallback_size():
    service = LLMService()
    service.client.embedding_enabled = False
    vector = await service.embed("테스트 임베딩")
    assert vector is not None
    assert len(vector) == get_settings().qdrant_vector_size


@pytest.mark.asyncio
async def test_llm_classification_fallback():
    service = LLMService()
    service.client.summary_enabled = False
    category = await service.classify_category("장학금 신청 안내")
    assert category in get_settings().llm_categories
