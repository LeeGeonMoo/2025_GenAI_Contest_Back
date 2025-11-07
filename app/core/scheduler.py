"""
APScheduler integration for ingest/notification jobs.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.ingest.pipeline import IngestPipeline
from app.ingest.sources.dummy import DummyNoticeSource

scheduler: Optional[AsyncIOScheduler] = None


async def start_scheduler() -> None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        return

    global scheduler
    if scheduler is not None:
        return

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    pipeline = IngestPipeline(sources=[DummyNoticeSource()])

    async def run_pipeline() -> None:
        await pipeline.run()

    scheduler.add_job(
        lambda: asyncio.create_task(run_pipeline()),
        trigger="interval",
        minutes=settings.scheduler_interval_minutes,
        id="ingest_pipeline",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()


async def shutdown_scheduler() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None
