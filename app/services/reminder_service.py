from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from beanie import PydanticObjectId

from app.models.reminder import Reminder


class ReminderService:
    async def create_reminder(
        self,
        user_id: str,
        post_id: str,
        notify_at: datetime,
        channel: str,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            post_id=post_id,
            notify_at=notify_at,
            channel=channel,
            status="scheduled",
        )
        await reminder.insert()
        return reminder

    async def list_reminders(
        self,
        user_id: str,
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        query = Reminder.find(Reminder.user_id == user_id)
        total = await query.count()
        reminders = (
            await query.sort(Reminder.notify_at).skip((page - 1) * page_size).limit(page_size).to_list()
        )
        return {
            "items": reminders,
            "meta": {"total": total, "page": page, "page_size": page_size},
        }
