from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from beanie import Document, Indexed
from pydantic import Field


class Post(Document):
    title: str
    url: str
    posted_at: datetime = Field(default_factory=datetime.utcnow)
    deadline_at: Optional[datetime] = None
    body: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    college: Optional[str] = None
    department: Optional[str] = None
    audience_grade: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    source: Optional[str] = None
    hash: Indexed(str, unique=True)  # Prevent duplicates from ingest
    likes: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "posts"
        use_revision = False
        indexes = [
            "department",
            "audience_grade",
            [("deadline_at", 1)],
            [("posted_at", -1)],
        ]
