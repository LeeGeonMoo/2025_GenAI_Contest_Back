from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from app.ingest.catalog import BoardEntry
from app.ingest.sources.html_base import HTMLNoticeSource
from app.ingest.sources.snu_scholarship import SNUScholarshipHTMLSource
from app.ingest.sources.wordpress import WordpressListSource

logger = logging.getLogger(__name__)


TEMPLATE_MAP: Dict[str, Type[HTMLNoticeSource]] = {
    "wordpress_board": WordpressListSource,
    "wordpress-list": WordpressListSource,
    "snu_scholarship_html": SNUScholarshipHTMLSource,
}


def create_source(entry: BoardEntry) -> Optional[HTMLNoticeSource]:
    cls = TEMPLATE_MAP.get(entry.template)
    if not cls:
        logger.warning("No adapter for template %s (board %s)", entry.template, entry.id)
        return None
    metadata = {
        "college": entry.college,
        "department": entry.department,
        "board_id": entry.id,
    }
    return cls(entry.url, metadata=metadata, options=entry.options or {})
