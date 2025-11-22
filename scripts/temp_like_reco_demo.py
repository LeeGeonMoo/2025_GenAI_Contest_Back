"""
Temporary script to validate like-based recommendations end-to-end.
Creates a dummy user + posts, upserts vectors to Qdrant, runs reco, then cleans up.

Usage (from repo root):
    python scripts/temp_like_reco_demo.py
"""

from __future__ import annotations

import asyncio
import random
import string
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from qdrant_client.models import FieldCondition, Filter, MatchValue

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.mongo import init_db
from app.db.qdrant import get_qdrant_client
from app.models.post import Post
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.recommendation_service import RecommendationService
from app.services import vector_store


def _rand_suffix(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


async def upsert_post_with_vector(title: str, category: str, suffix: str) -> Post:
    now = datetime.now(timezone.utc)
    post = Post(
        title=title,
        url=f"https://example.com/{suffix}",
        posted_at=now - timedelta(days=1),
        deadline_at=now + timedelta(days=7),
        body=f"{category} 관련 내용입니다. suffix={suffix}",
        summary=f"{category} 요약",
        tags=[category],
        college="Engineering",
        department="컴퓨터공학부",
        audience_grade=["3", "4"],
        category=category,
        source="temp-reco-demo",
        hash=f"temp-reco-demo-{suffix}",
    )
    await post.insert()

    llm = LLMService()
    vector = await llm.embed(f"{post.title}\n{post.summary}\n{post.body}")
    if vector:
        payload = {
            "post_id": str(post.id),
            "department": post.department,
            "audience_grade": post.audience_grade,
            "posted_at": post.posted_at.isoformat(),
            "deadline_at": post.deadline_at.isoformat() if post.deadline_at else None,
            "tags": post.tags,
            "category": post.category,
            "source": post.source,
        }
        await vector_store.upsert_notice_vector(
            post_id=str(post.id),
            vector=vector,
            payload=payload,
        )
    return post


async def cleanup(user: User, posts: list[Post]) -> None:
    # Delete user and posts
    if user.id:
        await user.delete()
    for post in posts:
        await post.delete()

    # Remove associated vectors from Qdrant
    client = get_qdrant_client()
    post_ids = [str(p.id) for p in posts]
    client.delete(
        collection_name="notice_vectors",
        points_selector=Filter(
            must=[FieldCondition(key="post_id", match=MatchValue(value=pid)) for pid in post_ids]
        ),
    )


async def main() -> None:
    await init_db()
    suffix = _rand_suffix()

    # Create dummy posts and embed them
    posts = [
        await upsert_post_with_vector("더미 장학 공지", "장학", suffix + "a"),
        await upsert_post_with_vector("더미 인턴십 공지", "인턴십", suffix + "b"),
        await upsert_post_with_vector("더미 행사 공지", "행사", suffix + "c"),
    ]

    user = User(email=f"temp-user-{suffix}@example.com", liked_post_ids=[str(posts[0].id), str(posts[1].id)])
    await user.insert()

    reco = RecommendationService()
    result = await reco.like_recommendations(user_id=str(user.id), limit=5)

    print("=== Liked posts ===")
    for p in posts[:2]:
        print(f"- {p.title} | category={p.category} | id={p.id}")

    print("\n=== Recommendation result ===")
    print("meta:", result.get("meta"))
    for item in result.get("items", []):
        reason = item.get("reason") or ""
        print(
            f"- {item.get('title')} | category={item.get('category')} | "
            f"id={item.get('_id') or item.get('id')} | score={item.get('semantic_score')} | reason={reason}"
        )

    # Clean up created data
    await cleanup(user, posts)
    print("Cleanup completed.")


if __name__ == "__main__":
    asyncio.run(main())
