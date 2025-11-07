"""
Seed script to create sample users and like/save interactions for testing
recommendation flows.

Usage:
    docker compose exec api python scripts/seed_users.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.db.mongo import close_db, init_db
from app.models.interaction import Interaction
from app.models.post import Post
from app.models.user import User


async def seed_users() -> None:
    await init_db()

    user = await User.find_one(User.email == "student1@snu.ac.kr")
    if not user:
        user = User(
            email="student1@snu.ac.kr",
            college="공과대학",
            department="컴퓨터공학부",
            grade="3",
            interests=["인턴십", "장학금"],
        )
        await user.insert()

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
