"""
Test script to embed a natural-language query and search Qdrant for similar notices.

Usage:
    docker compose exec api python scripts/search_qdrant.py "장학금 신청 마감 안내"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beanie import PydanticObjectId

from app.db.mongo import close_db, init_db
from app.models.post import Post
from app.services import vector_store
from app.services.llm_service import LLMService


async def main(query: str) -> None:
    await init_db()
    llm = LLMService()
    vector = await llm.embed(query)
    if not vector:
        print("Failed to produce embedding; check LLM embedding configuration.")
        return

    hits = await vector_store.search_similar(vector, limit=5)
    if not hits:
        print("No hits returned from Qdrant.")
        return

    raw_ids = [
        hit.get("payload", {}).get("post_id")
        for hit in hits
        if hit.get("payload", {}).get("post_id")
    ]
    cast_ids = []
    for raw in raw_ids:
        if raw and PydanticObjectId.is_valid(raw):
            cast_ids.append(PydanticObjectId(raw))

    posts = await Post.find({Post.id: {"$in": cast_ids}}).to_list() if cast_ids else []
    post_map = {str(post.id): post for post in posts}

    for hit in hits:
        payload = hit.get("payload", {})
        post_id = payload.get("post_id")
        print(f"- score={hit.get('score'):.4f} post_id={post_id}")
        if post_id in post_map:
            post = post_map[post_id]
            print(f"  title: {post.title}")
            print(f"  category: {post.category}")
            summary = (post.summary or "")[:200]
            print(f"  summary: {summary}")
            print()
        else:
            print("  (no Post document found)")

    await close_db()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query_text = " ".join(sys.argv[1:])
    else:
        query_text = "인턴"
    asyncio.run(main(query_text))
