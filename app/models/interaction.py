from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Indexed
from pydantic import Field


class Interaction(Document):
    user_id: Indexed(str)
    post_id: Indexed(str)
    type: Literal["view", "like", "save"]
    ts: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None

    class Settings:
        name = "interactions"
        use_revision = False
        indexes = [
            [("user_id", 1), ("post_id", 1), ("type", 1)],
        ]
