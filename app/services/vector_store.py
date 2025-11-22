from __future__ import annotations

import asyncio
import logging
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from qdrant_client.models import Distance, FieldCondition, Filter, MatchAny, MatchValue, PointStruct, VectorParams

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


async def search_similar_with_filter(
    vector: List[float],
    post_ids: List[str],
    limit: int,
    offset: int = 0,
) -> List[Dict]:
    """
    Search for similar vectors within a filtered set of post_ids.
    """
    if not post_ids:
        return []
    
    await ensure_collection()
    client = get_qdrant_client()
    
    def _search() -> List[Dict]:
        result = client.search(
            collection_name=get_settings().qdrant_collection_notices,
            query_vector=vector,
            limit=limit + offset,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="post_id",
                        match=MatchAny(any=post_ids)
                    )
                ]
            ),
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


async def fetch_vectors_by_post_ids(post_ids: Iterable[str]) -> Dict[str, List[float]]:
    """
    Fetch stored notice vectors by their post_id payload.
    Returns a mapping of post_id -> vector (first match per post).
    """
    ids = list(post_ids)
    if not ids:
        return {}

    await ensure_collection()
    client = get_qdrant_client()

    def _fetch() -> Dict[str, List[float]]:
        vectors: Dict[str, List[float]] = {}
        for pid in ids:
            points, _ = client.scroll(
                collection_name=get_settings().qdrant_collection_notices,
                limit=1,
                with_vectors=True,
                scroll_filter=Filter(
                    must=[FieldCondition(key="post_id", match=MatchValue(value=pid))]
                ),
            )
            if not points:
                continue
            vector = points[0].vector
            # vector may be dict when using named vectors; handle list/dict gracefully
            if isinstance(vector, dict):
                # take the first vector if multiple names exist
                try:
                    vector = next(iter(vector.values()))
                except StopIteration:
                    continue
            if isinstance(vector, list):
                vectors[pid] = vector
        return vectors

    return await asyncio.to_thread(_fetch)
