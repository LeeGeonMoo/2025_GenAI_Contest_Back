from __future__ import annotations

from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.models.interaction import Interaction
from app.models.post import Post
from app.models.user import User


class InteractionService:
    """
    Handles likes/saves interactions and keeps user preference cache in sync.
    """

    async def like_post(self, user_id: str, post_id: str) -> dict:
        user = await User.get(user_id)
        if not user:
            raise ValueError("User not found")

        post = await Post.get(post_id)
        if not post:
            raise ValueError("Post not found")

        interaction = await Interaction.find_one(
            Interaction.user_id == user_id,
            Interaction.post_id == post_id,
            Interaction.type == "like",
        )
        if interaction:
            return {"status": "exists"}

        await Interaction(
            user_id=user_id,
            post_id=post_id,
            type="like",
            ts=datetime.utcnow(),
        ).insert()

        liked_ids = set(user.liked_post_ids or [])
        liked_ids.add(post_id)
        user.liked_post_ids = list(liked_ids)
        await user.save()

        post.likes += 1
        await post.save()

        return {"status": "liked", "post_id": post_id}

    async def unlike_post(self, user_id: str, post_id: str) -> dict:
        user = await User.get(user_id)
        if not user:
            raise ValueError("User not found")

        interaction = await Interaction.find_one(
            Interaction.user_id == user_id,
            Interaction.post_id == post_id,
            Interaction.type == "like",
        )
        if interaction:
            await interaction.delete()

        if user.liked_post_ids:
            user.liked_post_ids = [
                pid for pid in user.liked_post_ids if pid != post_id
            ]
            await user.save()

        post = await Post.get(post_id)
        if post and post.likes > 0:
            post.likes -= 1
            await post.save()

        return {"status": "unliked", "post_id": post_id}
