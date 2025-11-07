from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List

from bs4 import BeautifulSoup

from app.ingest.base import RawNotice
from app.ingest.sources.html_base import HTMLNoticeSource

KST = timezone(timedelta(hours=9))


class SNUScholarshipHTMLSource(HTMLNoticeSource):
    name = "snu-scholarship-html"

    def __init__(
        self,
        url: str | None,
        metadata: dict | None = None,
        options: dict | None = None,
    ) -> None:
        super().__init__(url, metadata, options)

    def parse(self, html: str) -> List[RawNotice]:
        soup = BeautifulSoup(html, "html.parser")
        notices: List[RawNotice] = []
        articles = soup.select("section.notices article.notice")
        for article in articles:
            title_el = article.select_one("h2.title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href") or ""
            body_el = article.select_one(".body")
            body = body_el.get_text(" ", strip=True) if body_el else ""
            posted_text = article.select_one(".meta .posted")
            deadline_text = article.select_one(".meta .deadline")
            posted_at = self._parse_date(posted_text.get_text(strip=True) if posted_text else None)
            deadline_at = self._parse_date(deadline_text.get_text(strip=True) if deadline_text else None)
            department = article.get("data-department")
            grades = article.get("data-grade", "")
            audience = [grade.strip() for grade in grades.split(",") if grade.strip()]
            category = article.get("data-category")
            tags = [li.get_text(strip=True) for li in article.select("ul.tags li")]

            notices.append(
                RawNotice(
                    source=self.name,
                    title=title,
                    url=url,
                    body=body,
                    posted_at=posted_at,
                    deadline_at=deadline_at,
                    college=self.metadata.get("college"),
                    department=department or self.metadata.get("department"),
                    audience_grade=audience or self.metadata.get("audience_grade", []),
                    tags=tags,
                    category=category or self.metadata.get("category"),
                )
            )
        return notices

    def _parse_date(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(tz=KST)
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt
