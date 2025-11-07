from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Protocol


@dataclass
class RawNotice:
    source: str
    title: str
    url: str
    body: str
    posted_at: datetime
    deadline_at: datetime | None = None
    college: str | None = None
    department: str | None = None
    audience_grade: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    category: str | None = None


@dataclass
class NormalizedNotice:
    title: str
    url: str
    body: str
    summary: str | None
    posted_at: datetime
    deadline_at: datetime | None
    tags: List[str]
    college: str | None
    department: str | None
    audience_grade: List[str]
    category: str | None
    source: str


class NoticeSource(Protocol):
    """
    Represents a single board/source that can produce raw notices.
    """

    name: str

    async def fetch(self) -> List[RawNotice]:
        ...
