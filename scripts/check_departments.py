#!/usr/bin/env python3
"""Check what department values exist in the database."""
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.models.post import Post
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    await init_beanie(database=client.notisnu, document_models=[Post])

    # Get sample posts
    posts = await Post.find({}).limit(20).to_list()
    depts = set(p.department for p in posts if p.department)

    print(f"Found {len(posts)} posts")
    print(f"Unique departments: {len(depts)}")
    print("\nSample departments in DB:")
    for d in sorted(depts):
        print(f"  - '{d}'")

    # Also check what source values are being sent from frontend
    print("\n--- Frontend sends these values (from source.name) ---")
    print("Example: '전기정보공학부', '컴퓨터공학부', '사범대학', etc.")


if __name__ == "__main__":
    asyncio.run(main())

