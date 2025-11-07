from __future__ import annotations

import hashlib
from typing import List

from app.ingest.base import NormalizedNotice, RawNotice


def summarize(body: str) -> str:
    """Fallback summarizer used before LLM summary overrides."""
    body = body.strip()
    return body if len(body) <= 120 else f"{body[:117]}..."


def normalize(raw: RawNotice) -> NormalizedNotice:
    summary = summarize(raw.body)
    tags = raw.tags or extract_tags(raw)
    audience = raw.audience_grade or ["1", "2", "3", "4"]
    return NormalizedNotice(
        title=raw.title,
        url=raw.url,
        body=raw.body,
        summary=summary,
        posted_at=raw.posted_at,
        deadline_at=raw.deadline_at,
        tags=tags,
        college=raw.college,
        department=raw.department,
        audience_grade=audience,
        category=raw.category,
        source=raw.source,
    )


def extract_tags(raw: RawNotice) -> List[str]:
    keywords = []
    text = f"{raw.title} {raw.body}".lower()
    if any(keyword in text for keyword in ("scholarship", "scholar", "장학")):
        keywords.append("scholarship")
    if any(keyword in text for keyword in ("intern", "field practice", "현장실습")):
        keywords.append("internship")
    if raw.department:
        keywords.append(raw.department)
    if not keywords:
        keywords.append("general")
    return keywords


def hash_notice(title: str, body: str, posted_at) -> str:
    value = f"{title}|{body}|{posted_at.isoformat()}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()
