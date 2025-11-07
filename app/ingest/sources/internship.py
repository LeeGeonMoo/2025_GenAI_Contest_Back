from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from app.ingest.base import NoticeSource, RawNotice

KST = timezone(timedelta(hours=9))


class InternshipNoticeSource(NoticeSource):
    name = "internship-board"

    async def fetch(self) -> List[RawNotice]:
        now = datetime.now(tz=KST)
        return [
            RawNotice(
                source=self.name,
                title="IT 스타트업 겨울 인턴 모집",
                url="https://dummy.snu.ac.kr/intern/it-winter",
                body="컴퓨터공학·산업공학 학생 대상 8주 인턴십. 11월 30일까지 지원.",
                posted_at=now - timedelta(days=1),
                deadline_at=now + timedelta(days=8),
                college="공과대학",
                department="컴퓨터공학부",
                audience_grade=["3", "4"],
                tags=["인턴십", "IT"],
                category="진로",
            ),
            RawNotice(
                source=self.name,
                title="대기업 R&D 인턴십",
                url="https://dummy.snu.ac.kr/intern/rnd",
                body="화학생물공학/재료공학 학생 대상 R&D 인턴십. 12월 5일 마감.",
                posted_at=now - timedelta(days=4),
                deadline_at=now + timedelta(days=12),
                college="공과대학",
                department="화학생물공학부",
                audience_grade=["3", "4"],
                tags=["인턴십", "R&D"],
                category="연구",
            ),
        ]
