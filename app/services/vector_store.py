from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from uuid import uuid4

from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import get_settings
from app.db.qdrant import get_qdrant_client

logger = logging.getLogger(__name__)

_collection_initialized = False


async def ensure_collection() -> None:
    global _collection_initialized
    if _collection_initialized:
        return

    settings = get_settings()
    client = get_qdrant_client()

    def _ensure() -> None:
        collections = client.get_collections().collections
        names = [c.name for c in collections]
        if settings.qdrant_collection_notices in names:
            return
        client.recreate_collection(
            collection_name=settings.qdrant_collection_notices,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,
                distance=Distance.COSINE,
            ),
        )

    await asyncio.to_thread(_ensure)
    _collection_initialized = True


async def upsert_notice_vector(post_id: str, vector: List[float], payload: Dict) -> None:
    await ensure_collection()
    client = get_qdrant_client()

    payload = {"post_id": post_id, **payload}
    point = PointStruct(id=str(uuid4()), vector=vector, payload=payload)
    await asyncio.to_thread(
        client.upsert,
        collection_name=get_settings().qdrant_collection_notices,
        points=[point],
    )


async def search_similar(
    vector: List[float],
    limit: int,
    offset: int = 0,
) -> List[Dict]:
    await ensure_collection()
    client = get_qdrant_client()

    def _search() -> List[Dict]:
        result = client.search(
            collection_name=get_settings().qdrant_collection_notices,
            query_vector=vector,
            limit=limit + offset,
        )
        return [
            {
                "id": str(point.id),
                "score": point.score,
                "payload": point.payload or {},
                "post_id": (point.payload or {}).get("post_id"),
            }
            for point in result
        ]

    hits = await asyncio.to_thread(_search)
    return hits[offset:limit + offset]
