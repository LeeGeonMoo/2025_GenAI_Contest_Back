"""
Seed script to insert sample posts into MongoDB for local testing.

Run inside the API container:
    docker compose exec api python scripts/seed_posts.py
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.mongo import close_db, init_db
from app.models.post import Post

KST = timezone(timedelta(hours=9))


def _make_hash(title: str, body: str, posted_at: datetime) -> str:
    value = f"{title}|{body}|{posted_at.isoformat()}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


SAMPLE_POSTS = [
    {
        "title": "공학대 학부연구생 모집 안내",
        "url": "https://dept.snu.ac.kr/notice/123",
        "posted_at": datetime.now(tz=KST) - timedelta(days=1),
        "deadline_at": datetime.now(tz=KST) + timedelta(days=6),
        "body": "공학대 연구실에서 학부연구생을 모집합니다. 관심 있는 학생은 11월 15일까지 지원서를 제출하세요.",
        "summary": "공학대 학부연구생 선발, 11월 15일까지 지원",
        "tags": ["연구", "학부연구생", "공학대"],
        "college": "공과대학",
        "department": "전기정보공학부",
        "audience_grade": ["3", "4"],
        "category": "연구",
    },
    {
        "title": "사회과학대 장학금 신청 안내",
        "url": "https://dept.snu.ac.kr/notice/456",
        "posted_at": datetime.now(tz=KST) - timedelta(days=2),
        "deadline_at": datetime.now(tz=KST) + timedelta(days=3),
        "body": "사회과학대 재학생을 위한 2025년도 1학기 장학금 신청을 받습니다. 신청 기간은 11월 10일까지입니다.",
        "summary": "사회대 장학금 신청, 11월 10일 마감",
        "tags": ["장학금", "사회대"],
        "college": "사회과학대학",
        "department": "정치외교학부",
        "audience_grade": ["1", "2", "3", "4"],
        "category": "장학",
    },
    {
        "title": "자연대 겨울 계절학기 현장실습",
        "url": "https://dept.snu.ac.kr/notice/789",
        "posted_at": datetime.now(tz=KST) - timedelta(days=3),
        "deadline_at": datetime.now(tz=KST) + timedelta(days=1),
        "body": "자연대 겨울 계절학기 현장실습 프로그램 참가자를 모집합니다. 현장실습 시간은 12월~1월 예정입니다.",
        "summary": "자연대 겨울 현장실습 참가자 모집",
        "tags": ["현장실습", "자연대"],
        "college": "자연과학대학",
        "department": "물리천문학부",
        "audience_grade": ["2", "3", "4"],
        "category": "진로",
    },
]


async def seed_posts() -> None:
    await init_db()
    for post in SAMPLE_POSTS:
        hash_value = _make_hash(post["title"], post["body"], post["posted_at"])
        existing = await Post.find_one(Post.hash == hash_value)
        if existing:
            continue

        await Post(
            hash=hash_value,
            likes=0,
            source="seed_posts",
            **post,
        ).insert()
    await close_db()


if __name__ == "__main__":
    asyncio.run(seed_posts())
