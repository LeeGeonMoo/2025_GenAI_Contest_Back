"""
Print a few sample notices (title/category/summary) for debugging.

Usage:
    docker compose exec api python scripts/peek_posts.py
"""

from __future__ import annotations

import asyncio

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.mongo import init_db, close_db
from app.models.post import Post


async def main() -> None:
    await init_db()
    docs = (
        await Post.find({"source": "local-dummy-dataset"})
        .sort(-Post.created_at)
        .limit(5)
        .to_list()
    )
    if not docs:
        print("No posts found with source=local-dummy-dataset.")
    for doc in docs:
        print(f"- {doc.title}")
        print(f"  category: {doc.category}")
        print(f"  summary: {(doc.summary or '')[:200]}")
        print(f"  body: {(doc.body or '')[:240]}{'...' if doc.body and len(doc.body) > 240 else ''}")
        print()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
