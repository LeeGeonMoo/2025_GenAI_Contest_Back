"""Board catalog loader mapping board entries to parser templates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class BoardEntry:
    id: str
    college: str
    department: str
    url: str
    template: str
    requires_auth: bool = False
    notes: Optional[str] = None
    options: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "BoardEntry":
        return cls(
            id=data["id"],
            college=data.get("college", ""),
            department=data.get("department", ""),
            url=data["url"],
            template=data.get("template", ""),
            requires_auth=data.get("requires_auth", False),
            notes=data.get("notes"),
            options=data.get("options") or {},
        )


def load_catalog(path: str | Path) -> List[BoardEntry]:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    return [BoardEntry.from_dict(entry) for entry in data]
