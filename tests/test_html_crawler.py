from pathlib import Path

from app.ingest.sources.snu_scholarship import SNUScholarshipHTMLSource
from app.ingest.sources.wordpress import WordpressListSource


def test_html_parser_extracts_notices():
    source = SNUScholarshipHTMLSource(None, metadata={"college": "Test College"})
    html = Path("docs/sample_pages/scholarship_board.html").read_text(encoding="utf-8")

    notices = source.parse(html)

    assert len(notices) == 2
    assert notices[0].title == "AI 장학금 지원 안내"
    assert "장학금" in notices[0].tags


def test_wordpress_parser_works_with_sample():
    source = WordpressListSource(
        None,
        metadata={"college": "Test", "department": "TestDept"},
    )
    html = Path("docs/sample_pages/scholarship_board.html").read_text(encoding="utf-8")

    notices = source.parse(html)
    assert notices
