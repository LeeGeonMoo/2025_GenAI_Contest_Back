from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.core.config import get_settings
from app.models.post import Post
from app.models.user import User
from app.models.interaction import Interaction
from app.models.reminder import Reminder

mongo_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    """
    Connect to MongoDB and initialise Beanie with all document models.
    """
    global mongo_client
    if mongo_client is not None:
        return

    settings = get_settings()
    mongo_client = AsyncIOMotorClient(settings.mongo_url)
    await init_beanie(
        database=mongo_client[settings.mongo_db],
        document_models=[Post, User, Interaction, Reminder],
    )


async def close_db() -> None:
    global mongo_client
    if mongo_client is None:
        return
    mongo_client.close()
    mongo_client = None
