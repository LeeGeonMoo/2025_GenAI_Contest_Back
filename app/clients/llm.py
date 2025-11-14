from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """HTTP client wrapper for summary/classification and embedding endpoints."""

    def __init__(self) -> None:
        settings = get_settings()

        self.summary_base = settings.llm_summary_base or settings.llm_api_base
        self.summary_key = settings.llm_summary_key or settings.llm_api_key
        self.summary_endpoint = settings.llm_summary_endpoint
        self.summary_model = settings.llm_summary_model
        self.summary_max_tokens = settings.llm_summary_max_tokens
        self.summary_timeout = settings.llm_summary_timeout or settings.llm_api_timeout

        self.chat_base = settings.llm_chat_base or self.summary_base or settings.llm_api_base
        self.chat_key = settings.llm_chat_key or self.summary_key or settings.llm_api_key
        self.chat_endpoint = settings.llm_chat_endpoint
        self.chat_model = settings.llm_chat_model or self.summary_model
        self.chat_max_tokens = settings.llm_chat_max_tokens
        self.chat_timeout = (
            settings.llm_chat_timeout
            or self.summary_timeout
            or settings.llm_api_timeout
        )

        self.embedding_base = settings.llm_embedding_base or settings.llm_api_base
        self.embedding_key = settings.llm_embedding_key or settings.llm_api_key
        self.embedding_endpoint = settings.llm_embedding_endpoint
        self.embedding_model = settings.llm_embedding_model
        self.embedding_timeout = settings.llm_embedding_timeout or settings.llm_api_timeout

        self.summary_enabled = bool(self.summary_base and self.summary_key)
        self.chat_enabled = bool(self.chat_base and self.chat_key)
        self.embedding_enabled = bool(self.embedding_base and self.embedding_key)

        if not self.summary_enabled:
            logger.info("LLM summary client disabled (missing base URL or API key).")
        if not self.chat_enabled:
            logger.info("LLM chat client disabled (missing base URL or API key).")
        if not self.embedding_enabled:
            logger.info("LLM embedding client disabled (missing base URL or API key).")

    async def generate_summary(self, text: str) -> str:
        if not self.summary_enabled:
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
        response = await self._post(
            base=self.summary_base,
            api_key=self.summary_key,
            endpoint=self.summary_endpoint,
            timeout=self.summary_timeout,
            payload=payload,
        )
        try:
            return response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMRequestError("Invalid summary response payload") from exc

    async def embed_text(self, text: str) -> List[float]:
        if not self.embedding_enabled:
            raise LLMDisabledError("LLM client not configured")

        payload = {
            "model": self.embedding_model,
            "input": text,
        }
        response = await self._post(
            base=self.embedding_base,
            api_key=self.embedding_key,
            endpoint=self.embedding_endpoint,
            timeout=self.embedding_timeout,
            payload=payload,
        )
        try:
            return response["data"][0]["embedding"]
        except (KeyError, IndexError) as exc:
            raise LLMRequestError("Invalid embedding response payload") from exc

    async def classify_text(self, text: str, categories: List[str]) -> str:
        if not self.summary_enabled:
            raise LLMDisabledError("LLM client not configured")

        category_list = ", ".join(categories)
        prompt = (
            "다음 공지 내용을 읽고 아래 범주 중 하나만 반환하세요.\n"
            f"가능한 범주: {category_list}\n\n"
            f"공지: {text}"
        )
        payload = {
            "model": self.summary_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You classify university notices into one of the provided categories.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 16,
        }
        response = await self._post(
            base=self.summary_base,
            api_key=self.summary_key,
            endpoint=self.summary_endpoint,
            timeout=self.summary_timeout,
            payload=payload,
        )
        try:
            return response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMRequestError("Invalid classification response payload") from exc

    async def chat_completion(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: float = 0.1,
    ) -> str:
        if not self.chat_enabled:
            raise LLMDisabledError("LLM chat client not configured")

        payload = {
            "model": self.chat_model,
            "messages": messages,
            "max_tokens": max_tokens or self.chat_max_tokens,
            "temperature": temperature,
        }
        response = await self._post(
            base=self.chat_base,
            api_key=self.chat_key,
            endpoint=self.chat_endpoint,
            timeout=self.chat_timeout,
            payload=payload,
        )
        try:
            return response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMRequestError("Invalid chat response payload") from exc

    async def _post(
        self,
        base: Optional[str],
        api_key: Optional[str],
        endpoint: str,
        timeout: float,
        payload: dict,
    ) -> dict:
        if not base or not api_key:
            raise LLMDisabledError("LLM client not configured")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = f"{base.rstrip('/')}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=timeout) as client:
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
