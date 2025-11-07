from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from app.ingest.base import NoticeSource, RawNotice

KST = timezone(timedelta(hours=9))


class ScholarshipNoticeSource(NoticeSource):
    name = "scholarship-board"

    async def fetch(self) -> List[RawNotice]:
        now = datetime.now(tz=KST)
        return [
            RawNotice(
                source=self.name,
                title="인문대 장학금 신청 안내",
                url="https://dummy.snu.ac.kr/scholarship/2025",
                body="인문대 2~4학년 장학금 신청을 11월 20일까지 받습니다.",
                posted_at=now - timedelta(days=2),
                deadline_at=now + timedelta(days=4),
                college="인문대학",
                department="국어국문학과",
                audience_grade=["2", "3", "4"],
                tags=["장학금", "인문대"],
                category="장학",
            ),
            RawNotice(
                source=self.name,
                title="사범대 교육봉사 장학 프로그램",
                url="https://dummy.snu.ac.kr/scholarship/teach",
                body="교육봉사 활동 참여자에게 장학금을 지급합니다. 12월 1일까지 신청.",
                posted_at=now - timedelta(days=3),
                deadline_at=now + timedelta(days=10),
                college="사범대학",
                department="교육학과",
                audience_grade=["1", "2", "3", "4"],
                tags=["장학금", "봉사"],
                category="봉사",
            ),
        ]
