from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Minimal HTTP client wrapper for summary and embedding endpoints.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.llm_api_base
        self.api_key = settings.llm_api_key
        self.summary_endpoint = settings.llm_summary_endpoint
        self.embedding_endpoint = settings.llm_embedding_endpoint
        self.summary_model = settings.llm_summary_model
        self.embedding_model = settings.llm_embedding_model
        self.summary_max_tokens = settings.llm_summary_max_tokens
        self.timeout = settings.llm_api_timeout

        self.enabled = bool(self.base_url and self.api_key)
        if not self.enabled:
            logger.info("LLM client disabled (missing base URL or API key).")

    async def generate_summary(self, text: str) -> str:
        if not self.enabled:
            raise LLMDisabledError("LLM client not configured")

        payload = {
            "model": self.summary_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise assistant that summarizes university notices.",
                },
                {"role": "user", "content": text},
            ],
            "max_tokens": self.summary_max_tokens,
        }
        response = await self._post(self.summary_endpoint, payload)
        try:
            return response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMRequestError("Invalid summary response payload") from exc

    async def embed_text(self, text: str) -> List[float]:
        if not self.enabled:
            raise LLMDisabledError("LLM client not configured")

        payload = {
            "model": self.embedding_model,
            "input": text,
        }
        response = await self._post(self.embedding_endpoint, payload)
        try:
            return response["data"][0]["embedding"]
        except (KeyError, IndexError) as exc:
            raise LLMRequestError("Invalid embedding response payload") from exc

    async def _post(self, endpoint: str, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("LLM request failed: %s", exc)
                raise LLMRequestError(str(exc)) from exc
            return resp.json()


class LLMRequestError(Exception):
    """Raised when the LLM HTTP request fails or returns malformed data."""


class LLMDisabledError(Exception):
    """Raised when the LLM client is not configured/enabled."""


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient()
