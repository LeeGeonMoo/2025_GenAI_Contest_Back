"""
Qdrant client factory.
"""

from qdrant_client import QdrantClient

from app.core.config import get_settings

client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """
    Lazily instantiate and return a shared Qdrant client.
    """
    global client
    if client is None:
        settings = get_settings()
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return client
