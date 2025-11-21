"""
Seed script to create sample users and like/save interactions for testing
recommendation flows.

Usage:
    docker compose exec api python scripts/seed_users.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.mongo import close_db, init_db
from app.models.interaction import Interaction
from app.models.post import Post
from app.models.user import User


async def seed_users() -> None:
    await init_db()

    # 프론트엔드에서 사용하는 테스트용 user 생성
    user = await User.find_one(User.email == "lgmoo2002@snu.ac.kr")
    if not user:
        user = User(
            email="lgmoo2002@snu.ac.kr",
            name="이건무",
            college="공과대학",
            department="기계공학부",
            grade="4",
            interests=["채용/인턴", "AI/데이터"],
        )
        await user.insert()
        print(f"Created user: {user.email} ({user.id})")
    else:
        print(f"User already exists: {user.email} ({user.id})")

    posts = await Post.find().sort(-Post.posted_at).limit(3).to_list()
    liked_ids = [str(post.id) for post in posts]
    user.liked_post_ids = liked_ids
    await user.save()

    for post_id in liked_ids:
        exists = await Interaction.find_one(
            Interaction.user_id == str(user.id),
            Interaction.post_id == post_id,
            Interaction.type == "like",
        )
        if exists:
            continue
        await Interaction(
            user_id=str(user.id),
            post_id=post_id,
            type="like",
            ts=datetime.utcnow(),
        ).insert()

    await close_db()
    print(f"Seeded user {user.email} ({user.id}) with likes: {liked_ids}")


if __name__ == "__main__":
    asyncio.run(seed_users())
