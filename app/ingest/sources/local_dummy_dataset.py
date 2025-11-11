from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup

from app.ingest.base import RawNotice
from app.ingest.sources.html_base import HTMLNoticeSource

KST = timezone(timedelta(hours=9))


class LocalDummyDatasetSource(HTMLNoticeSource):
    """
    Loads locally generated HTML notices for rapid prototyping.
    """

    name = "local-dummy-dataset"

    def __init__(self, directory: str) -> None:
        super().__init__(url=None, metadata={"college": "Dummy College"}, options=None)
        self.directory = Path(directory)

    async def fetch(self) -> List[RawNotice]:
        notices: List[RawNotice] = []
        for file_path in sorted(self.directory.glob("notice_*.html")):
            html = file_path.read_text(encoding="utf-8")
            notices.extend(self.parse(html))
        return notices

    def parse(self, html: str) -> List[RawNotice]:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article.notice")
        results: List[RawNotice] = []
        for article in articles:
            title_el = article.select_one("h2.title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href") or ""
            body = article.select_one(".body").get_text(" ", strip=True)
            posted_at = self._parse_date(article.select_one(".meta .posted"))
            deadline_at = self._parse_date(article.select_one(".meta .deadline"))
            department = article.get("data-department")
            grades = [
                grade.strip()
                for grade in (article.get("data-grade") or "").split(",")
                if grade.strip()
            ]
            category = article.get("data-category")
            tags = [li.get_text(strip=True) for li in article.select("ul.tags li")]
            results.append(
                RawNotice(
                    source=self.name,
                    title=title,
                    url=url,
                    body=body,
                    posted_at=posted_at,
                    deadline_at=deadline_at,
                    college="Dummy College",
                    department=department,
                    audience_grade=grades,
                    tags=tags,
                    category=category,
                )
            )
        return results

    def _parse_date(self, node) -> datetime:
        if node is None:
            return datetime.now(tz=KST)
        text = node.get_text(strip=True)
        try:
            dt = datetime.strptime(text, "%Y-%m-%d")
            return dt.replace(tzinfo=KST)
        except ValueError:
            return datetime.now(tz=KST)
