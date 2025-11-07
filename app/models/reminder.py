from __future__ import annotations

from datetime import datetime
from typing import Literal

from beanie import Document, Indexed
from pydantic import Field


class Reminder(Document):
    user_id: Indexed(str)
    post_id: Indexed(str)
    notify_at: datetime
    channel: Literal["email", "kakao"]
    status: Literal["scheduled", "sent", "failed"] = "scheduled"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "reminders"
        use_revision = False
        indexes = [
            [("user_id", 1), ("notify_at", 1)],
            [("post_id", 1), ("notify_at", 1)],
        ]
