from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from beanie import Document, Indexed
from pydantic import Field


class User(Document):
    email: Indexed(str, unique=True)
    college: Optional[str] = None
    department: Optional[str] = None
    grade: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    liked_post_ids: List[str] = Field(default_factory=list)
    preference_vector_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        use_revision = False
