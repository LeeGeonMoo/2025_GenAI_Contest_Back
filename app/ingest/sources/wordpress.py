from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.ingest.base import RawNotice
from app.ingest.sources.html_base import HTMLNoticeSource

KST = timezone(timedelta(hours=9))


class WordpressListSource(HTMLNoticeSource):
    """
    Heuristic parser for common WordPress list layouts (article/li/card).
    """

    name = "wordpress-list"

    def parse(self, html: str) -> List[RawNotice]:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article")
        if not articles:
            articles = soup.select(".board-list li, .posts-list li, ul.post li")

        notices: List[RawNotice] = []
        for item in articles:
            title_el = item.select_one("a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = self._resolve_url(title_el.get("href"))
            body = self._extract_excerpt(item)
            posted_at = self._parse_date(item.select_one("time, .posted, .date"))
            deadline_at = None
            tags = [tag.get_text(strip=True) for tag in item.select(".tags a, .cat-links a")]

            notices.append(
                RawNotice(
                    source=self.name,
                    title=title,
                    url=url,
                    body=body,
                    posted_at=posted_at,
                    deadline_at=deadline_at,
                    college=self.metadata.get("college"),
                    department=self.metadata.get("department"),
                    audience_grade=self.metadata.get("audience_grade", []),
                    tags=tags,
                    category=self.metadata.get("category"),
                )
            )
        return notices

    def _extract_excerpt(self, element) -> str:
        target = element.select_one(".entry-summary, .excerpt, p")
        if target:
            return target.get_text(" ", strip=True)
        return ""

    def _parse_date(self, node) -> datetime:
        if node is None:
            return datetime.now(tz=KST)
        text = node.get("datetime") or node.get_text(strip=True)
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.replace(tzinfo=KST)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt
        except ValueError:
            return datetime.now(tz=KST)

    def _resolve_url(self, href: Optional[str]) -> str:
        if not href:
            return self._current_base_url or self.url or ""
        if href.startswith("http"):
            return href
        return urljoin(self._current_base_url or self.url or "", href)
