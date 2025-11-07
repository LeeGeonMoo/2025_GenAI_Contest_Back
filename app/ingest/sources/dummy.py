from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from app.ingest.base import NoticeSource, RawNotice

KST = timezone(timedelta(hours=9))


class DummyNoticeSource(NoticeSource):
    name = "dummy-source"

    async def fetch(self) -> List[RawNotice]:
        now = datetime.now(tz=KST)
        return [
            RawNotice(
                source=self.name,
                title="Dummy 장학금 안내",
                url="https://dummy.snu.ac.kr/notice/1",
                body="장학금 신청은 11월 20일까지입니다.",
                posted_at=now - timedelta(days=1),
                deadline_at=now + timedelta(days=5),
                college="사회과학대학",
                department="경제학부",
                audience_grade=["1", "2", "3", "4"],
                tags=["장학금", "신청"],
                category="장학",
            )
        ]
