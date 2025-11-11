"""
Run the ingest pipeline with dummy notice sources.

Usage:
    docker compose exec api python scripts/run_ingest.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.ingest.adapters import create_source
from app.ingest.catalog import load_catalog
from app.ingest.pipeline import IngestPipeline
from app.ingest.sources.dummy import DummyNoticeSource
from app.ingest.sources.scholarship import ScholarshipNoticeSource
from app.ingest.sources.internship import InternshipNoticeSource
from app.ingest.sources.snu_scholarship import SNUScholarshipHTMLSource
from app.ingest.sources.local_dummy_dataset import LocalDummyDatasetSource


async def main() -> None:
    settings = get_settings()
    sources = [
        DummyNoticeSource(),
        ScholarshipNoticeSource(),
        InternshipNoticeSource(),
    ]
    sources.append(LocalDummyDatasetSource("docs/dummy_notices"))
    if settings.crawler_sample_html:
        sources.append(SNUScholarshipHTMLSource(settings.crawler_sample_html))

    if settings.board_catalog_enabled and settings.board_catalog_path:
        try:
            entries = load_catalog(settings.board_catalog_path)
            for entry in entries:
                source = create_source(entry)
                if source:
                    sources.append(source)
        except FileNotFoundError:
            print(f"[warn] catalog not found: {settings.board_catalog_path}")

    pipeline = IngestPipeline(sources=sources)
    result = await pipeline.run()
    print(f"Ingest completed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
