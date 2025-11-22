from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, List

from bs4 import BeautifulSoup

from app.ingest.base import RawNotice
from app.ingest.sources.html_base import HTMLNoticeSource

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


class LocalDummyJSONSource(HTMLNoticeSource):
    """
    Loads curated dummy notices from a JSON file (one or more JSON arrays).
    Expects records similar to docs/dummy_data/dummy_samples.txt.
    """

    name = "local-dummy-json"

    def __init__(self, path: str) -> None:
        super().__init__(url=None, metadata={"college": "Dummy College"}, options=None)
        self.path = Path(path)

    async def fetch(self) -> List[RawNotice]:
        if not self.path.exists():
            logger.warning("Dummy JSON file not found: %s", self.path)
            return []
        content = self.path.read_text(encoding="utf-8")
        records = self._load_arrays(content)
        notices: List[RawNotice] = []
        for rec in records:
            notice = self._to_notice(rec)
            if notice:
                notices.append(notice)
        return notices

    def parse(self, html: str) -> List[RawNotice]:
        """
        Not used for JSON source (HTMLNoticeSource requires this method).
        """
        return []

    def _load_arrays(self, content: str) -> List[dict]:
        """
        The file may contain multiple JSON arrays concatenated.
        Parse them sequentially using JSONDecoder.raw_decode.
        """
        decoder = json.JSONDecoder()
        idx = 0
        cleaned: List[dict] = []
        length = len(content)
        while idx < length:
            # Skip whitespace/newlines
            while idx < length and content[idx].isspace():
                idx += 1
            if idx >= length:
                break
            try:
                obj, end = decoder.raw_decode(content, idx)
                idx = end
                if isinstance(obj, list):
                    cleaned.extend([item for item in obj if isinstance(item, dict)])
                elif isinstance(obj, dict):
                    cleaned.append(obj)
            except json.JSONDecodeError:
                idx += 1
                continue
        return cleaned

    def _to_notice(self, rec: dict) -> RawNotice | None:
        try:
            title = rec.get("title") or ""
            if not title:
                return None
            url = rec.get("source_url") or rec.get("url") or ""
            body_html = rec.get("body_html") or ""
            body_text = self._html_to_text(body_html)

            posted_at = self._parse_date(rec.get("posted"))
            deadline_at = self._parse_date(rec.get("deadline")) if rec.get("deadline") else None
            tags = rec.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            grades = rec.get("grades") or []
            if isinstance(grades, str):
                grades = [g.strip() for g in grades.split(",") if g.strip()]

            return RawNotice(
                source=self.name,
                title=title,
                url=url,
                body=body_text,
                posted_at=posted_at,
                deadline_at=deadline_at,
                college=rec.get("college") or "Dummy College",
                department=rec.get("department"),
                audience_grade=grades,
                tags=tags,
                category=rec.get("category"),
            )
        except Exception as exc:  # pragma: no cover - defensive against malformed records
            logger.warning("Failed to convert dummy record: %s", exc)
            return None

    def _parse_date(self, value) -> datetime:
        if not value:
            return datetime.now(tz=KST)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=KST)
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y.%m.%d %H:%M", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt = datetime.strptime(str(value), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
                return dt
            except ValueError:
                continue
        return datetime.now(tz=KST)

    def _html_to_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(" ", strip=True)
