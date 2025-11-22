from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import asyncio
import re
import time

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
        # Reason-generation tuning knobs
        self.reason_top_k = 3
        self.reason_liked_k = 3
        self.reason_cache_ttl = 15 * 60  # 15 minutes
        self.reason_timeout = 3.0  # seconds
        self._reason_cache: Dict[str, tuple[float, str]] = {}

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

        liked_ids = self._collect_liked_ids(user)
        
        # 2. Rule-based 필터링
        filters = self._build_filters(user)
        exclude_object_ids = self._object_ids_from_strings(liked_ids)
        if exclude_object_ids:
            filters["_id"] = {"$nin": exclude_object_ids}
        # 최신순으로 정렬하여 상위 limit * 4개를 후보군으로 선정
        filtered_posts = (
            await Post.find(filters)
            .sort(-Post.posted_at)
            .limit(limit * 4)
            .to_list()
        )
        filtered_posts = self._filter_posts_by_likes(filtered_posts, liked_ids)
        
        if not filtered_posts:
            return await self._fallback_feed(limit, liked_ids)
        
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
        final_items = self._filter_items_by_likes(final_items, liked_ids)
        
        # 7. 포맷팅 및 반환
        return await self._format_response(final_items[:limit], limit)

    async def like_recommendations(
        self,
        user_id: Optional[str],
        limit: int,
    ) -> Dict[str, Any]:
        user, liked_posts = await self._fetch_user_and_likes(user_id)
        semantic = await self._semantic_from_likes(user, liked_posts, limit)
        if semantic:
            return semantic

        return {"items": [], "meta": {"total": 0, "page": 1, "page_size": limit, "total_pages": 0}}

    async def _semantic_from_likes(
        self,
        user: Optional[User],
        ordered_liked_posts: List[Post],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        if not user or not ordered_liked_posts:
            return None

        combined_text = " ".join(
            filter(None, [(post.summary or post.body) for post in ordered_liked_posts])
        ).strip()
        vector = await self._user_vector(ordered_liked_posts, combined_text)
        if not vector:
            return None

        attempts = 0
        max_attempts = 3
        search_limit = limit * 2
        max_limit = limit * 8
        items: List[Dict[str, Any]] = []

        exclude_ids = {str(post.id) for post in ordered_liked_posts}

        while attempts <= max_attempts and search_limit <= max_limit:
            hits = await vector_store.search_similar(vector, limit=search_limit)
            items = await self._posts_from_hits(
                hits,
                exclude_ids,
                limit,
                user_id=str(user.id),
                liked_posts=ordered_liked_posts,
            )
            if len(items) >= limit or search_limit >= max_limit:
                break
            attempts += 1
            search_limit *= 2

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
        user_id: Optional[str],
        liked_posts: List[Post],
    ) -> List[Dict[str, Any]]:
        def _extract_post_id(hit: Dict[str, Any]) -> Optional[str]:
            return hit.get("post_id") or hit.get("payload", {}).get("post_id") or hit.get("id")

        ordered_ids = [
            ObjectId(post_id)
            for post_id in (_extract_post_id(hit) for hit in hits)
            if post_id and ObjectId.is_valid(post_id) and post_id not in exclude_ids
        ]
        if not ordered_ids:
            return []

        posts = await Post.find(In(Post.id, ordered_ids)).to_list()
        post_map = {str(post.id): post for post in posts}

        items: List[Dict[str, Any]] = []
        reason_budget = limit  # generate reasons for all recommended items
        for idx, hit in enumerate(hits):
            post_id = _extract_post_id(hit)
            if not post_id:
                continue
            if post_id in exclude_ids:
                continue
            post = post_map.get(post_id)
            if not post:
                continue
            formatted_item = self.feed_service._format_post_item(post)
            formatted_item["semantic_score"] = hit.get("score")
            formatted_item["reason"] = ""
            if len(items) < reason_budget:
                reason = await self._build_reason(
                    user_id=user_id,
                    liked_posts=liked_posts,
                    candidate=post,
                )
                formatted_item["reason"] = reason
            items.append(formatted_item)
            if len(items) >= limit:
                break
        return items

    async def _build_reason(
        self,
        user_id: Optional[str],
        liked_posts: List[Post],
        candidate: Post,
    ) -> str:
        if not liked_posts:
            return self._friendly_reason("좋아요가 부족해 이유를 만들지 못했어요.")

        cache_key = self._reason_cache_key(user_id, candidate, liked_posts)
        cached = self._get_reason_cache(cache_key)
        if cached is not None:
            return cached

        similar_likes = await self._select_similar_likes(candidate, liked_posts)
        if not similar_likes:
            similar_likes = liked_posts[: self.reason_liked_k]

        liked_lines = "\n".join(
            f"- {self._post_brief(post)}" for post in similar_likes[: self.reason_liked_k]
        )
        candidate_line = f"- {self._post_brief(candidate)}"
        user_prompt = (
            "좋아요 기반으로 비슷한 공지를 추천합니다.\n"
            "근거로 사용된 좋아요 공지:\n"
            f"{liked_lines}\n\n"
            "추천 후보 공지:\n"
            f"{candidate_line}\n\n"
            '출력 형식: "<한 줄 이유>" (30~60자, 한국어)'
        )
        system_prompt = (
    "두 공지의 공통점을 분석하여 추천 사유를 작성합니다. 다음 예시의 톤앤매너를 따르세요.\n\n"
    "예시 1:\n"
    "- 좋아요한 공지: 현대자동차 AI 채용연계형 인턴\n"
    "- 후보 공지: 삼성전자 SW 아카데미 모집\n"
    "- 출력: 💡 좋아요를 눌렀던 SW/AI 분야의 커리어 개발 기회입니다.\n\n"
    "예시 2:\n"
    "- 좋아요한 공지: 2024학년도 2학기 국가장학금 신청\n"
    "- 후보 공지: 교외 00재단 생활비 장학금\n"
    "- 출력: 💰 지난 번에 본 소득분위 기반 장학금 혜택과 유사해요.\n\n"
    "위와 같이 핵심 키워드를 포함하여 30자 이내의 한국어 한 줄로 설명하세요."
)

        try:
            response = await asyncio.wait_for(
                self.llm_service.client.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=64,
                    temperature=0.2,
                ),
                timeout=self.reason_timeout,
            )
            reason = self._clean_reason(response)
        except Exception:
            reason = ""

        if not reason:
            reason = self._heuristic_reason(liked_posts, candidate)

        reason = self._friendly_reason(reason)

        if cache_key and reason:
            self._set_reason_cache(cache_key, reason)
        return reason

    async def _select_similar_likes(
        self,
        candidate: Post,
        liked_posts: List[Post],
    ) -> List[Post]:
        """
        Pick top-N liked posts most similar to the candidate using stored vectors.
        Falls back to recent likes when vectors are missing.
        """
        if not liked_posts:
            return []

        liked_ids = [str(post.id) for post in liked_posts]
        vectors = await vector_store.fetch_vectors_by_post_ids([str(candidate.id), *liked_ids])
        cand_vec = vectors.get(str(candidate.id))

        if not cand_vec:
            # Try to embed candidate on the fly as a fallback
            text = " ".join(
                filter(
                    None,
                    [
                        candidate.title,
                        candidate.summary,
                        candidate.body,
                    ],
                )
            )
            emb = await self.llm_service.embed(text)
            cand_vec = self._l2_normalize(emb) if emb else None
        else:
            cand_vec = self._l2_normalize(cand_vec)

        if not cand_vec:
            return liked_posts[: self.reason_liked_k]

        scored: List[tuple[float, Post]] = []
        for post in liked_posts:
            vec = vectors.get(str(post.id))
            if not vec:
                continue
            sim = self._cosine_similarity(cand_vec, self._l2_normalize(vec))
            if sim is not None:
                scored.append((sim, post))

        if not scored:
            return liked_posts[: self.reason_liked_k]

        scored.sort(key=lambda x: x[0], reverse=True)
        return [post for _, post in scored[: self.reason_liked_k]]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> Optional[float]:
        if not a or not b or len(a) != len(b):
            return None
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return None
        return dot / (norm_a * norm_b)

    def _post_brief(self, post: Post) -> str:
        parts = [post.title]
        tags = ", ".join((post.tags or [])[:3])
        extras = []
        if tags:
            extras.append(tags)
        if post.category:
            extras.append(post.category)
        if post.deadline_at:
            extras.append(f"마감 {post.deadline_at.date().isoformat()}")
        if extras:
            parts.append(f"({' | '.join(extras)})")
        return " ".join(parts)

    def _clean_reason(self, text: str) -> str:
        reason = (text or "").strip()
        if not reason:
            return ""
        if len(reason) > 80:
            reason = reason[:80].rstrip()
        return reason

    def _friendly_reason(self, text: str) -> str:
        reason = (text or "").strip()
        if not reason:
            return ""

        reason = re.sub(r"\s+", " ", reason)
        # remove duplicated "추천해요" style prefixes while keeping leading emoji/symbols
        reason = re.sub(
            r"^([\W_]{0,3})?추천해요[:\s-]*",
            r"\1",
            reason,
            flags=re.IGNORECASE,
        ).strip()
        reason = re.sub(
            r"^추천\s*(?:이유|사유)[:\s-]*",
            "",
            reason,
            flags=re.IGNORECASE,
        ).strip()

        if not reason:
            return ""

        polite_endings = (
            "요",
            "요.",
            "에요",
            "에요.",
            "이에요",
            "이에요.",
            "입니다",
            "입니다.",
            "습니다",
            "습니다.",
            "다",
            "다.",
        )
        if not reason.endswith(polite_endings):
            if reason[-1] in ".!?":
                pass
            else:
                reason = reason.rstrip(". ") + "입니다."

        return reason.strip()

    def _heuristic_reason(self, liked_posts: List[Post], candidate: Post) -> str:
        cand_tags = set(candidate.tags or [])
        liked_tags: set[str] = set()
        liked_cats: set[str] = set()
        for post in liked_posts:
            liked_tags.update(post.tags or [])
            if post.category:
                liked_cats.add(post.category)

        overlap_tags = list(cand_tags & liked_tags)
        if overlap_tags:
            joined = ", ".join(overlap_tags[:2])
            return f"{joined} 관심사가 겹칩니다"

        if candidate.category and candidate.category in liked_cats:
            return f"{candidate.category} 분야 관심과 가깝습니다"

        if candidate.tags:
            return f"{candidate.tags[0]} 주제와 연관됩니다"

        return "최근 좋아한 공지와 주제가 비슷합니다"

    def _reason_cache_key(
        self,
        user_id: Optional[str],
        candidate: Post,
        liked_posts: List[Post],
    ) -> str:
        if not user_id:
            return ""
        liked_ids = [str(post.id) for post in liked_posts[:5]]
        liked_sig = "|".join(liked_ids)
        return f"{user_id}:{str(candidate.id)}:{liked_sig}"

    def _get_reason_cache(self, key: str) -> Optional[str]:
        if not key:
            return None
        entry = self._reason_cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            self._reason_cache.pop(key, None)
            return None
        return value

    def _set_reason_cache(self, key: str, value: str) -> None:
        expires_at = time.time() + self.reason_cache_ttl
        self._reason_cache[key] = (expires_at, value)
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

    def _collect_liked_ids(self, user: Optional[User]) -> Set[str]:
        if not user or not user.liked_post_ids:
            return set()
        return {pid for pid in user.liked_post_ids if pid}

    def _object_ids_from_strings(self, ids: Set[str]) -> List[ObjectId]:
        object_ids: List[ObjectId] = []
        for pid in ids:
            try:
                if pid and ObjectId.is_valid(pid):
                    object_ids.append(ObjectId(pid))
            except (TypeError, ValueError):
                continue
        return object_ids

    def _filter_posts_by_likes(
        self,
        posts: List[Post],
        liked_ids: Set[str],
    ) -> List[Post]:
        if not liked_ids:
            return posts
        return [post for post in posts if str(post.id) not in liked_ids]

    def _filter_items_by_likes(
        self,
        items: List[Dict[str, Any]],
        liked_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        if not liked_ids:
            return items
        return [item for item in items if item.get("id") not in liked_ids]

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

    async def _fallback_feed(self, limit: int, exclude_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
        """
        Fallback: 기본 피드 반환
        """
        return await self.feed_service.get_feed(
            category=None,
            page=1,
            page_size=limit,
            exclude_ids=exclude_ids if exclude_ids else None,
        )

    async def _fetch_user_and_likes(
        self,
        user_id: Optional[str],
    ) -> Tuple[Optional[User], List[Post]]:
        if not user_id:
            return None, []
        user = await User.get(user_id)
        if not user or not user.liked_post_ids:
            return user, []

        object_ids: List[ObjectId] = []
        for post_id in user.liked_post_ids:
            try:
                if post_id and ObjectId.is_valid(post_id):
                    object_ids.append(ObjectId(post_id))
            except (TypeError, ValueError):
                continue
        if not object_ids:
            return user, []

        liked_posts = await Post.find(In(Post.id, object_ids)).to_list()
        liked_map = {str(post.id): post for post in liked_posts}
        ordered_liked_posts = [
            liked_map[pid] for pid in user.liked_post_ids if pid in liked_map
        ]
        return user, ordered_liked_posts
