from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Indexed
from pydantic import Field


class Conversation(Document):
    user_id: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "conversations"
        use_revision = False
        indexes = [
            "user_id",
            [("updated_at", -1)],
        ]


class Message(Document):
    conversation_id: Indexed(str)
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "messages"
        use_revision = False
        indexes = [
            [("conversation_id", 1), ("created_at", -1)],
        ]
