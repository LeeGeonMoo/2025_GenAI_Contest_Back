from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.ingest.base import NoticeSource, RawNotice


class HTMLNoticeSource(NoticeSource, ABC):
    """
    Base class for HTML-based crawlers. Fetches HTML via HTTP or local file and
    delegates parsing to subclasses. Metadata such as college/department is
    injected via `metadata`.
    """

    name: str = "html-source"

    def __init__(
        self,
        url: Optional[str],
        metadata: Optional[Dict] = None,
        options: Optional[Dict] = None,
    ) -> None:
        self.url = url
        self.metadata = metadata or {}
        self.options = options or {}
        self.settings = get_settings()
        self._current_base_url: Optional[str] = url

    async def fetch(self) -> List[RawNotice]:
        if not self.url:
            return []
        notices: List[RawNotice] = []
        for target_url in self._iter_page_urls():
            html = await self._load_html(target_url)
            if not html:
                # If a subsequent page fails (e.g., 404), stop pagination.
                if target_url != self.url:
                    break
                continue
            self._current_base_url = target_url
            parsed = self.parse(html)
            notices.extend(parsed)
        return notices

    async def _load_html(self, url: str) -> Optional[str]:
        if url.startswith("file://"):
            path = url.replace("file://", "", 1)
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            return await asyncio.to_thread(self._read_file, path)
        if os.path.exists(url):
            return await asyncio.to_thread(self._read_file, url)
        timeout = self.settings.crawler_request_timeout
        verify = self.settings.crawler_verify_ssl
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as exc:
            logger.warning("Failed to fetch %s (status %s)", url, exc.response.status_code)
            return None
        except httpx.HTTPError as exc:
            logger.error("HTTP error fetching %s: %s", url, exc)
            return None

    def _read_file(self, path: str) -> Optional[str]:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _iter_page_urls(self) -> List[str]:
        pagination = self.options.get("pagination")
        if not pagination:
            return [self.url] if self.url else []

        urls: List[str] = []
        max_pages = pagination.get("max_pages", 1)
        start = pagination.get("start", 1)
        strategy = pagination.get("type", "query")
        param = pagination.get("param", "page")

        if not self.url:
            return []

        if strategy == "path":
            base = self.url.rstrip("/")
            for page in range(start, start + max_pages):
                if page <= 1:
                    urls.append(self.url)
                else:
                    urls.append(f"{base}/page/{page}/")
        else:  # query
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

            parsed = urlparse(self.url)
            base_query = parse_qs(parsed.query)
            for page in range(start, start + max_pages):
                if page <= 1:
                    urls.append(self.url)
                    continue
                query = base_query.copy()
                query[param] = [str(page)]
                new_query = urlencode(query, doseq=True)
                urls.append(urlunparse(parsed._replace(query=new_query)))

        # Deduplicate while preserving order
        seen = set()
        ordered = []
        for target in urls:
            if target not in seen:
                ordered.append(target)
                seen.add(target)
        return ordered

    @abstractmethod
    def parse(self, html: str) -> List[RawNotice]:
        ...
logger = logging.getLogger(__name__)
