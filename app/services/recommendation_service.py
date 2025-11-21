from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from beanie.operators import In
from bson import ObjectId

from app.models.post import Post
from app.models.user import User
from app.services import vector_store
from app.services.feed_service import FeedService
from app.services.llm_service import LLMService


class RecommendationService:
    """
    Provides profile-based feed plus semantic similarity recommendations using
    user likes. Falls back to baseline feed when insufficient data is present.
    """

    def __init__(
        self,
        feed_service: FeedService | None = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self.feed_service = feed_service or FeedService()
        self.llm_service = llm_service or LLMService()

    async def profile_recommendations(
        self,
        user_id: str,
        limit: int,
    ) -> Dict[str, Any]:
        """
        사용자 프로필 기반 추천 피드 생성
        1. Rule-based 필터링 (interests → category, grade)
        2. LLM으로 프로필 문장 생성
        3. 문장 임베딩
        4. 벡터 유사도 검색 (필터링된 포스트들 중)
        5. 하이브리드 보정 (학년 필터링, 마감일 보정)
        """
        # 1. 사용자 정보 조회
        user = await User.get(user_id)
        if not user:
            return await self._fallback_feed(limit)
        
        # 2. Rule-based 필터링
        filters = self._build_filters(user)
        # 최신순으로 정렬하여 상위 limit * 3개를 후보군으로 선정
        filtered_posts = await Post.find(filters).sort(-Post.posted_at).limit(limit * 3).to_list()
        
        if not filtered_posts:
            return await self._fallback_feed(limit)
        
        # 3. LLM으로 프로필 문장 생성
        profile_text = await self._build_profile_query(user)
        if not profile_text:
            # LLM 실패 시 필터링된 결과만 반환
            return await self._format_filtered_posts(filtered_posts[:limit], limit)
        
        # 4. 문장 임베딩
        profile_vector = await self.llm_service.embed(profile_text)
        if not profile_vector:
            # Embedding 실패 시 필터링된 결과만 반환
            return await self._format_filtered_posts(filtered_posts[:limit], limit)
        
        # 5. 벡터 유사도 검색 (필터링된 포스트들 중에서)
        filtered_post_ids = [str(post.id) for post in filtered_posts]
        hits = await vector_store.search_similar_with_filter(
            vector=profile_vector,
            post_ids=filtered_post_ids,
            limit=limit * 2,
        )
        
        if not hits:
            # 벡터 검색 결과 없음 시 필터링된 결과만 반환
            return await self._format_filtered_posts(filtered_posts[:limit], limit)
        
        # 6. 하이브리드 보정 및 정렬
        final_items = self._score_and_sort_posts(filtered_posts, hits, user)
        
        # 7. 포맷팅 및 반환
        return await self._format_response(final_items[:limit], limit)

    async def like_recommendations(
        self,
        user_id: Optional[str],
        limit: int,
    ) -> Dict[str, Any]:
        semantic = await self._semantic_from_likes(user_id, limit)
        if semantic:
            return semantic

        # fallback의 경우도 명세서 형식에 맞게 meta 수정
        fallback = await self.feed_service.get_feed(
            category=None,
            page=1,
            page_size=limit,
        )
        # fallback은 이미 올바른 형식이므로 그대로 반환
        return fallback

    async def _semantic_from_likes(
        self,
        user_id: Optional[str],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None

        user = await User.get(user_id)
        if not user or not user.liked_post_ids:
            return None

        object_ids = [
            ObjectId(post_id)
            for post_id in user.liked_post_ids[-5:]
            if ObjectId.is_valid(post_id)
        ]
        if not object_ids:
            return None

        liked_posts = await Post.find(In(Post.id, object_ids)).to_list()
        combined_text = " ".join(filter(None, [(post.summary or post.body) for post in liked_posts])).strip()
        vector = await self._user_vector(liked_posts, combined_text)
        if not vector:
            return None

        hits = await vector_store.search_similar(vector, limit=limit * 2)
        exclude_ids = {str(post.id) for post in liked_posts}
        items = await self._posts_from_hits(hits, exclude_ids, limit)
        if not items:
            return None

        return {
            "items": items,
            "meta": {
                "total": len(items),
                "page": 1,
                "page_size": limit,
                "total_pages": 1,
            },
        }

    async def _user_vector(self, liked_posts: List[Post], combined_text: str) -> Optional[List[float]]:
        """
        Build a user preference vector.
        - Few likes: re-embed the combined text to capture shared context.
        - Many likes: prefer averaging stored post vectors to save LLM calls.
        - Fallback: if averaging fails, attempt a fresh embed.
        """
        like_count = len(liked_posts)
        # For small samples, re-embed text (higher fidelity, small cost).
        if like_count <= 5 and combined_text:
            vector = await self.llm_service.embed(combined_text)
            if vector:
                return self._l2_normalize(vector)

        # Try averaging stored vectors from Qdrant.
        post_ids = [str(post.id) for post in liked_posts]
        stored = await vector_store.fetch_vectors_by_post_ids(post_ids)
        averaged = self._mean_vector(stored.values())
        if averaged:
            return averaged

        # Fallback to text embedding if averaging failed.
        if combined_text:
            vector = await self.llm_service.embed(combined_text)
            if vector:
                return self._l2_normalize(vector)
        return None

    def _mean_vector(self, vectors: Iterable[List[float]]) -> Optional[List[float]]:
        vectors = [vec for vec in vectors if vec]
        if not vectors:
            return None

        length = len(vectors[0])
        summed = [0.0] * length
        used = 0
        for vec in vectors:
            # Skip vectors with mismatched dimensions
            if len(vec) != length:
                continue
            for i, value in enumerate(vec):
                summed[i] += value
            used += 1
        if used == 0:
            return None
        averaged = [value / used for value in summed]
        return self._l2_normalize(averaged)

    def _l2_normalize(self, vector: List[float]) -> List[float]:
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]

    async def _posts_from_hits(
        self,
        hits: List[Dict[str, Any]],
        exclude_ids: set[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        def _extract_post_id(hit: Dict[str, Any]) -> Optional[str]:
            return hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")

        # semantic score 순서 유지 (hits는 이미 점수 순으로 정렬되어 있음)
        ordered_ids = [
            ObjectId(post_id)
            for post_id in (_extract_post_id(hit) for hit in hits)
            if post_id and ObjectId.is_valid(post_id) and post_id not in exclude_ids
        ]
        if not ordered_ids:
            return []

        posts = await Post.find(In(Post.id, ordered_ids)).to_list()
        post_map = {str(post.id): post for post in posts}

        # hits 순서대로 포스트를 가져와서 _format_post_item 사용
        items: List[Dict[str, Any]] = []
        for hit in hits:
            post_id = _extract_post_id(hit)
            if not post_id:
                continue
            if post_id in exclude_ids:
                continue
            post = post_map.get(post_id)
            if not post:
                continue
            # _format_post_item 사용하여 일관된 형식으로 변환
            formatted_item = self.feed_service._format_post_item(post)
            # 디버깅을 위해 semantic score 추가
            formatted_item["semantic_score"] = hit.get("score")
            items.append(formatted_item)
            if len(items) >= limit:
                break
        return items

    def _build_filters(self, user: User) -> Dict[str, Any]:
        """
        사용자 프로필 기반 MongoDB 필터 생성
        - Interests → Category 매핑
        - Grade → audience_grade 필터링
        """
        filters: Dict[str, Any] = {}
        
        # Interests → Category 매핑
        if user.interests:
            categories = self._map_interests_to_categories(user.interests)
            if categories:
                filters["category"] = {"$in": categories}
        
        # 학년 필터링 (audience_grade에 포함되어야 함)
        if user.grade:
            filters["audience_grade"] = user.grade
        
        return filters

    def _map_interests_to_categories(self, interests: List[str]) -> List[str]:
        """
        Interests를 Category로 매핑
        하나의 interest가 여러 category에 매핑될 수 있음
        """
        interest_to_categories = {
            # 커리어
            "채용/인턴": ["채용"],
            "취업설명회": ["채용"],
            "창업/스타트업": ["채용"],
            "자격증": ["채용"],
            # 학술/연구
            "연구/논문": ["연구"],
            "학술대회": ["연구", "대학생활"],
            "특강/세미나": ["연구", "대학생활"],
            # 교내생활
            "장학금": ["장학"],
            "근로/RA": ["장학", "대학생활"],
            "동아리/학생회": ["대학생활"],
            "행사/축제": ["대학생활"],
            # 대외활동
            "공모전": ["대외활동", "대학생활"],
            "봉사활동": ["대외활동", "대학생활"],
            "대외활동": ["대외활동"],
            # 기타
            "국제교류/어학": ["기타", "대외활동", "대학생활"],
            "AI/데이터": ["기타", "연구"],
        }
        
        categories = set()
        for interest in interests:
            # 하나의 interest가 여러 category에 매핑될 수 있음
            categories_list = interest_to_categories.get(interest, [])
            for category in categories_list:
                categories.add(category)
        
        return list(categories)

    async def _build_profile_query(self, user: User) -> str:
        """
        LLM을 사용하여 사용자 프로필을 자연어 문장으로 변환
        """
        # LLM으로 자연어 문장 생성
        prompt = f"""다음 사용자 정보를 바탕으로 관심사를 자연스러운 문장으로 표현해주세요:
- 학년: {user.grade or "미지정"}
- 학과: {user.department or "미지정"}
- 관심 분야: {', '.join(user.interests) if user.interests else "없음"}

예시: "나는 4학년이고, 채용, 인턴, 창업, 스타트업, 그리고 학술대회 정보에 관심이 있는 학생이야."
답변은 한 문장으로 간결하게 작성해주세요."""
        
        try:
            response = await self.llm_service.client.chat_completion(
                messages=[
                    {"role": "system", "content": "사용자 프로필을 자연스러운 문장으로 변환합니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.3
            )
            return response.strip()
        except Exception:
            # Fallback: 템플릿 기반
            return self._fallback_profile_text(user)

    def _fallback_profile_text(self, user: User) -> str:
        """
        LLM 실패 시 템플릿 기반으로 프로필 문장 생성
        """
        parts = []
        
        if user.grade:
            parts.append(f"{user.grade}학년")
        
        if user.department:
            parts.append(f"{user.department}")
        
        if user.interests:
            interests_text = ", ".join(user.interests)
            parts.append(f"{interests_text}에 관심이 있는 학생")
        
        if parts:
            return f"나는 {'이고, '.join(parts)}이야."
        return "대학 공지사항에 관심이 있는 학생이야."

    def _score_and_sort_posts(
        self,
        posts: List[Post],
        hits: List[Dict[str, Any]],
        user: User
    ) -> List[Dict[str, Any]]:
        """
        하이브리드 보정 및 정렬
        - 벡터 검색 결과(hits)에 있는 포스트만 대상
        - 학년 필터링 (3-4학년 사용자: 신입생/1학년 공지 점수 감소)
        - 최신성 보정 (마감일이 아직 안 지난 공지에 가산점)
        - 포맷팅된 항목에 semantic_score 포함하여 반환
        """
        scored_items = []
        hit_map = {hit.get("post_id"): hit.get("score", 0.0) for hit in hits}
        now = datetime.now(timezone.utc)
        
        for post in posts:
            post_id = str(post.id)
            if post_id not in hit_map:
                continue  # 벡터 검색 결과에 없는 포스트는 제외
            
            base_score = hit_map.get(post_id, 0.0)
            
            # 학년 필터링 (신입생 공지 제외)
            if user.grade and user.grade in ["3", "4"]:
                if "신입생" in post.title or "1학년" in post.title:
                    base_score *= 0.5  # 점수 감소
            
            # 최신성 보정 (마감일이 아직 안 지난 공지에 가산점)
            if post.deadline_at:
                # timezone-aware와 timezone-naive datetime 비교를 위해 처리
                deadline = post.deadline_at
                if deadline.tzinfo is None:
                    # timezone-naive인 경우 UTC로 가정
                    deadline = deadline.replace(tzinfo=timezone.utc)
                elif deadline.tzinfo != timezone.utc:
                    # UTC가 아닌 경우 UTC로 변환
                    deadline = deadline.astimezone(timezone.utc)
                
                if deadline > now:
                    base_score += 0.05  # 마감 전 공지 가산점
            else:
                # deadline_at이 None인 경우도 가산점 (마감일 없는 공지)
                base_score += 0.05
            
            # 포맷팅 및 점수 추가
            formatted = self.feed_service._format_post_item(post)
            formatted["semantic_score"] = base_score
            scored_items.append(formatted)
        
        scored_items.sort(key=lambda x: x["semantic_score"], reverse=True)
        return scored_items

    async def _format_response(self, items: List[Dict[str, Any]], limit: int) -> Dict[str, Any]:
        """
        추천 결과를 API 응답 형식으로 포맷팅
        """
        return {
            "items": items,
            "meta": {
                "total": len(items),
                "page": 1,
                "page_size": limit,
                "total_pages": 1,
            },
        }

    async def _format_filtered_posts(self, posts: List[Post], limit: int) -> Dict[str, Any]:
        """
        필터링된 포스트만 포맷팅 (벡터 검색 실패 시 사용)
        """
        items = [self.feed_service._format_post_item(post) for post in posts]
        
        return {
            "items": items,
            "meta": {
                "total": len(items),
                "page": 1,
                "page_size": limit,
                "total_pages": 1,
            },
        }

    async def _fallback_feed(self, limit: int) -> Dict[str, Any]:
        """
        Fallback: 기본 피드 반환
        """
        return await self.feed_service.get_feed(
            category=None,
            page=1,
            page_size=limit,
        )
