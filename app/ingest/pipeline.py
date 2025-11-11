from __future__ import annotations

from typing import Iterable, List, Optional

from app.db.mongo import init_db
from app.ingest.base import NormalizedNotice, NoticeSource
from app.ingest.normalizer import hash_notice, normalize
from app.models.post import Post
from app.services.llm_service import LLMService
from app.services import vector_store


class IngestPipeline:
    def __init__(
        self,
        sources: Iterable[NoticeSource],
        llm_service: Optional[LLMService] = None,
    ):
        self.sources = list(sources)
        self.llm_service = llm_service or LLMService()

    async def run(self) -> dict:
        await init_db()
        inserted = 0
        skipped = 0
        vectorized = 0

        for source in self.sources:
            raw_notices = await source.fetch()
            normalized_notices: List[NormalizedNotice] = [
                normalize(raw) for raw in raw_notices
            ]
            for notice in normalized_notices:
                hash_value = hash_notice(notice.title, notice.body, notice.posted_at)
                exists = await Post.find_one(Post.hash == hash_value)
                if exists:
                    skipped += 1
                    continue
                combined_text = f"{notice.title}\n\n{notice.body}"
                summary = await self.llm_service.summarize(combined_text)
                notice.summary = summary
                classification = await self.llm_service.classify_category(combined_text)
                notice.category = classification

                embeds = await self.llm_service.embed(combined_text)

                post = Post(
                    title=notice.title,
                    url=notice.url,
                    body=notice.body,
                    summary=notice.summary,
                    posted_at=notice.posted_at,
                    deadline_at=notice.deadline_at,
                    tags=notice.tags,
                    college=notice.college,
                    department=notice.department,
                    audience_grade=notice.audience_grade,
                    category=notice.category,
                    source=notice.source,
                    hash=hash_value,
                )
                await post.insert()
                inserted += 1
                if embeds:
                    payload = {
                        "post_id": str(post.id),
                        "department": notice.department,
                        "audience_grade": notice.audience_grade,
                        "posted_at": notice.posted_at.isoformat(),
                        "deadline_at": notice.deadline_at.isoformat()
                        if notice.deadline_at
                        else None,
                        "tags": notice.tags,
                        "category": notice.category,
                        "source": notice.source,
                    }
                    await vector_store.upsert_notice_vector(
                        post_id=str(post.id),
                        vector=embeds,
                        payload=payload,
                    )
                    vectorized += 1

        return {"inserted": inserted, "skipped": skipped, "vectorized": vectorized}
