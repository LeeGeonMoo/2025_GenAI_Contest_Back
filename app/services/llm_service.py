from __future__ import annotations

import hashlib
import logging
from typing import List, Optional

from app.clients.llm import LLMClient, LLMDisabledError, LLMRequestError, get_llm_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Provides summarisation and embedding helpers with graceful fallbacks when the
    external LLM is unavailable.
    """

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or get_llm_client()
        self.vector_size = get_settings().qdrant_vector_size

    async def summarize(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        try:
            return await self.client.generate_summary(text)
        except (LLMDisabledError, LLMRequestError) as exc:
            logger.warning("Falling back to heuristic summary: %s", exc)
            return self._fallback_summary(text)

    async def embed(self, text: str) -> Optional[List[float]]:
        text = text.strip()
        if not text:
            return None
        try:
            return await self.client.embed_text(text)
        except (LLMDisabledError, LLMRequestError) as exc:
            logger.warning("Falling back to pseudo embedding: %s", exc)
            return self._fallback_embedding(text)

    def _fallback_summary(self, text: str, limit: int = 160) -> str:
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    def _fallback_embedding(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Repeat the digest to reach the desired vector size
        bytes_needed = self.vector_size * 4  # floats
        repeated = (digest * ((bytes_needed // len(digest)) + 1))[:bytes_needed]
        vector = [
            (int.from_bytes(repeated[i : i + 4], "little", signed=False) % 1000) / 1000
            for i in range(0, bytes_needed, 4)
        ]
        return vector[: self.vector_size]
