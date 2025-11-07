from datetime import datetime, timedelta

from app.models.post import Post
from app.services.feed_service import FeedService


def _make_post(**overrides):
    base = {
        "title": "테스트 공지",
        "url": "https://example.com",
        "posted_at": datetime.utcnow() - timedelta(days=1),
        "deadline_at": datetime.utcnow() + timedelta(days=5),
        "body": "본문",
        "summary": "요약",
        "tags": ["test"],
        "college": "공과대학",
        "department": "전기정보공학부",
        "audience_grade": ["3", "4"],
        "category": "연구",
        "source": "test-source",
        "hash": "hash123",
        "likes": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    base.update(overrides)
    return Post.model_construct(**base)


def test_score_contains_reason_fields():
    service = FeedService()
    post = _make_post()

    scored = service._score_post(post, department="전기정보공학부", grade="3")

    assert "score" in scored
    assert scored["rank_reason"]["dept_match"] == 1.0
    assert scored["rank_reason"]["grade_match"] == 1.0


def test_deadline_boost_favors_urgent_notice():
    service = FeedService()
    urgent = _make_post(deadline_at=datetime.utcnow() + timedelta(days=1))
    relaxed = _make_post(deadline_at=datetime.utcnow() + timedelta(days=10))

    urgent_boost = service._deadline_boost(urgent)
    relaxed_boost = service._deadline_boost(relaxed)

    assert urgent_boost > relaxed_boost
