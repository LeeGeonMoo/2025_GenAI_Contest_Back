from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from beanie.operators import In
from bson import ObjectId

from app.clients.llm import LLMDisabledError, LLMRequestError
from app.models.post import Post
from app.services import vector_store
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "너는 서울대학교 공지 도우미 챗봇이다. 제공된 공지 내용만을 근거로 "
    "정확하고 간결한 답변을 한국어로 작성하라. 근거가 충분하지 않으면 "
    "\"해당 질문은 제공된 공지로 답변할 수 없습니다.\"라고 말하고 citations를 비워라."
)

OUT_OF_SCOPE_KEYWORDS = [
    "날씨",
    "기온",
    "미세먼지",
    "환율",
    "주식",
    "코스피",
    "환전",
    "운세",
    "로또",
    "축구",
    "야구",
    "농구",
    "영화",
    "맛집",
    "여행",
    "tour",
    "weather",
    "stock",
    "lotto",
    "kbo",
    "nba",
    "premier league",
]

ABUSIVE_KEYWORDS = [
    "똥",
    "섹스",
    "sex",
    "fuck",
    "shit",
    "bastard",
    "씨발",
    "시발",
    "개새",
    "18놈",
    "욕해",
    "porn",
    "야동",
]

VERIFICATION_PROMPT = (
    "너는 대학 공지 챗봇의 검수자이다. 사용자 질문과 챗봇 답변을 보고 답변이 질문을 "
    "직접적으로 해결하고 학교 공지 맥락에 어긋나지 않는지만 판단하라. 결과는 JSON으로만 반환한다."
)


class ChatService:
    """
    Retrieval augmented chat powered by MongoDB + Qdrant contexts.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        refusal_message: str = "해당 질문은 제공된 공지로 답변할 수 없습니다.",
        max_candidates: int = 8,
        max_context_items: int = 4,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        self.refusal_message = refusal_message
        self.max_candidates = max_candidates
        self.max_context_items = max_context_items

    async def answer(
        self,
        question: str,
        user_id: Optional[str] = None,
        department: Optional[str] = None,
        grade: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_question(question)
        if not normalized:
            return self._build_response(
                self._refusal_message_for_reason("empty_question", question),
                [],
                [],
                True,
                "empty_question",
                normalized,
            )

        guardrail_reason = self._guardrail_reason(normalized)
        if guardrail_reason:
            return self._build_response(
                self._refusal_message_for_reason(guardrail_reason, question),
                [],
                [],
                True,
                guardrail_reason,
                normalized,
            )

        contexts = await self._retrieve_contexts(
            normalized,
            department=department,
            grade=grade,
        )
        if not contexts:
            return self._build_response(
                self._refusal_message_for_reason("no_context", question),
                [],
                [],
                True,
                "no_context",
                normalized,
            )

        grounded = await self._generate_grounded_answer(normalized, contexts)
        if grounded is None:
            return self._build_response(
                self._refusal_message_for_reason("llm_unavailable", question),
                [],
                [],
                True,
                "llm_unavailable",
                normalized,
            )

        verified, reason = await self._verify_answer(
            normalized,
            grounded["answer"],
            grounded["citations"],
            contexts,
        )
        if not verified:
            logger.info("Verification rejected answer: %s", reason)
            return self._build_response(
                self._refusal_message_for_reason("verification_failed", question),
                [],
                [],
                True,
                "verification_failed",
                normalized,
            )

        response_meta = {
            "question": normalized,
            "refused": False,
            "reason": "success",
            "source": grounded.get("source", "llm"),
            "user_id": user_id,
        }
        return {
            "answer": grounded["answer"],
            "citations": grounded["citations"],
            "notices": contexts,
            "meta": response_meta,
        }

    async def _retrieve_contexts(
        self,
        question: str,
        department: Optional[str],
        grade: Optional[str],
    ) -> List[Dict[str, Any]]:
        semantic_candidates = await self._semantic_candidates(question)
        keyword_candidates = await self._keyword_candidates(question, department, grade)

        merged = self._merge_candidates(
            semantic_candidates,
            keyword_candidates,
            department,
            grade,
        )
        contexts: List[Dict[str, Any]] = []
        for candidate in merged[: self.max_context_items]:
            contexts.append(self._format_context(candidate["post"], candidate["score"], candidate["signals"]))
        return contexts

    async def _semantic_candidates(self, question: str) -> List[Tuple[Post, float]]:
        vector = await self.llm_service.embed(question)
        if not vector:
            return []

        hits = await vector_store.search_similar(vector, limit=self.max_candidates)
        if not hits:
            return []

        mongo_ids = [
            ObjectId(str(hit.get("post_id")))
            for hit in hits
            if hit.get("post_id") and ObjectId.is_valid(str(hit.get("post_id")))
        ]
        if not mongo_ids:
            return []

        posts = await Post.find(In(Post.id, mongo_ids)).to_list()
        post_map = {str(post.id): post for post in posts}

        semantic: List[Tuple[Post, float]] = []
        for hit in hits:
            post_id = str(hit.get("post_id"))
            post = post_map.get(post_id)
            if not post:
                continue
            semantic.append((post, float(hit.get("score", 0.0))))
        return semantic

    async def _keyword_candidates(
        self,
        question: str,
        department: Optional[str],
        grade: Optional[str],
    ) -> List[Post]:
        filters = self._build_filters(department, grade)
        regex_pattern = self._build_regex_pattern(question)
        if regex_pattern:
            regex = {"$regex": regex_pattern, "$options": "i"}
            filters["$or"] = [
                {"title": regex},
                {"summary": regex},
                {"body": regex},
            ]

        cursor = (
            Post.find(filters)
            .sort(-Post.posted_at)
            .limit(self.max_candidates)
        )
        return await cursor.to_list()

    def _merge_candidates(
        self,
        semantic: Sequence[Tuple[Post, float]],
        keyword: Sequence[Post],
        department: Optional[str],
        grade: Optional[str],
    ) -> List[Dict[str, Any]]:
        scored: Dict[str, Dict[str, Any]] = {}

        for rank, (post, score) in enumerate(semantic):
            pid = str(post.id)
            scored[pid] = {
                "post": post,
                "semantic_score": score,
                "semantic_rank": rank,
            }

        for rank, post in enumerate(keyword):
            pid = str(post.id)
            bucket = scored.setdefault(
                pid,
                {
                    "post": post,
                },
            )
            bucket["keyword_rank"] = rank

        combined: List[Dict[str, Any]] = []
        for pid, data in scored.items():
            post = data["post"]
            semantic_score = data.get("semantic_score")
            keyword_rank = data.get("keyword_rank")
            score = self._score_candidate(
                post,
                semantic_score,
                keyword_rank,
                department,
                grade,
            )
            combined.append(
                {
                    "post": post,
                    "score": score,
                    "signals": {
                        "semantic_score": semantic_score,
                        "keyword_rank": keyword_rank,
                    },
                }
            )
        combined.sort(key=lambda item: item["score"], reverse=True)
        return combined

    async def _generate_grounded_answer(
        self,
        question: str,
        contexts: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        context_block = self._render_context_block(contexts)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "사용자 질문:\n"
                    f"{question}\n\n"
                    "공지 목록:\n"
                    f"{context_block}\n\n"
                    "규칙:\n"
                    "1) 제공된 공지 이외의 지식을 사용하지 말 것\n"
                    "2) 각 주장에 참조할 공지의 post_id를 citations 배열에 담을 것\n"
                    "3) 정보가 부족하면 needs_more_context 값을 true로 설정\n"
                    '4) 반드시 다음 JSON 형태로만 응답 {"answer": "...", "citations": ["<post_id>"], "needs_more_context": false}\n'
                ),
            },
        ]
        try:
            content = await self.llm_service.client.chat_completion(
                messages=messages,
                max_tokens=480,
                temperature=0.2,
            )
        except (LLMDisabledError, LLMRequestError) as exc:
            logger.warning("LLM chat unavailable, falling back to template: %s", exc)
            return {
                "answer": self._fallback_answer(contexts),
                "citations": [ctx["post_id"] for ctx in contexts],
                "source": "fallback",
            }

        parsed = self._parse_llm_response(content, contexts)
        if parsed is None:
            logger.warning("Failed to parse LLM chat response: %s", content)
            return {
                "answer": self._fallback_answer(contexts),
                "citations": [ctx["post_id"] for ctx in contexts],
                "source": "fallback",
            }
        parsed["source"] = "llm"
        return parsed

    def _parse_llm_response(
        self,
        raw: str,
        contexts: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        answer = (payload.get("answer") or "").strip()
        citations = payload.get("citations") or []
        needs_more = bool(payload.get("needs_more_context"))

        if not answer or needs_more:
            return None

        valid_ids = {ctx["post_id"] for ctx in contexts}
        filtered = [cid for cid in citations if cid in valid_ids]
        if not filtered:
            return None
        return {"answer": answer, "citations": filtered}

    async def _verify_answer(
        self,
        question: str,
        answer: str,
        citations: Sequence[str],
        contexts: Sequence[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        stripped_answer = answer.strip()
        if not stripped_answer:
            return False, "empty_answer"

        client = self.llm_service.client
        if not getattr(client, "chat_enabled", False):
            return True, "verification_skipped_chat_disabled"

        messages = [
            {"role": "system", "content": VERIFICATION_PROMPT},
            {
                "role": "user",
                "content": (
                    "질문:\n"
                    f"{question}\n\n"
                    "챗봇 답변:\n"
                    f"{stripped_answer}\n\n"
                    "규칙: 답변이 질문의 의도에 부합하는지, 엉뚱한 주제를 다루지 않는지 확인한 뒤 "
                    '{"valid": true/false, "reason": "..."} JSON 으로만 답하라.'
                ),
            },
        ]
        try:
            decision = await client.chat_completion(
                messages=messages,
                max_tokens=120,
                temperature=0.0,
            )
        except (LLMDisabledError, LLMRequestError) as exc:
            logger.warning("Verification unavailable: %s", exc)
            return True, "verification_skipped_error"

        verdict = self._parse_verification_response(decision)
        if verdict is None:
            return True, "verification_skipped_invalid_json"
        return (bool(verdict.get("valid", True)), verdict.get("reason") or "")

    def _parse_verification_response(self, raw: str) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    def _score_candidate(
        self,
        post: Post,
        semantic_score: Optional[float],
        keyword_rank: Optional[int],
        department: Optional[str],
        grade: Optional[str],
    ) -> float:
        score = 0.0
        if semantic_score is not None:
            score += 0.5 * max(0.0, min(1.0, semantic_score))
        if keyword_rank is not None:
            score += 0.2 * (1 / (1 + keyword_rank))
        score += 0.2 * self._department_match(post, department)
        score += 0.1 * self._grade_match(post, grade)
        score += 0.1 * self._recency_score(post)
        return score

    def _department_match(self, post: Post, department: Optional[str]) -> float:
        if not department:
            return 0.6 if post.department else 0.4
        if department == post.department:
            return 1.0
        return 0.1

    def _grade_match(self, post: Post, grade: Optional[str]) -> float:
        if not grade:
            return 0.5
        if grade in (post.audience_grade or []):
            return 1.0
        return 0.2

    def _recency_score(self, post: Post) -> float:
        now = datetime.utcnow()
        delta_hours = max(0.0, (now - post.posted_at).total_seconds() / 3600)
        return max(0.1, 1 / (1 + delta_hours / 24))

    def _format_context(
        self,
        post: Post,
        score: float,
        signals: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "post_id": str(post.id),
            "title": post.title,
            "summary": post.summary or self._truncate(post.body, 200),
            "body_snippet": self._truncate(post.body, 480),
            "department": post.department,
            "audience_grade": post.audience_grade,
            "category": post.category,
            "source": post.source,
            "posted_at": post.posted_at.isoformat(),
            "deadline_at": post.deadline_at.isoformat() if post.deadline_at else None,
            "score": round(score, 4),
            "signals": signals,
        }

    def _render_context_block(self, contexts: Sequence[Dict[str, Any]]) -> str:
        blocks: List[str] = []
        for ctx in contexts:
            grades = ", ".join(ctx.get("audience_grade") or []) or "전체"
            block = (
                f"- post_id: {ctx['post_id']}\n"
                f"  제목: {ctx['title']}\n"
                f"  요약: {ctx.get('summary') or ''}\n"
                f"  본문 발췌: {ctx.get('body_snippet')}\n"
                f"  대상 학년: {grades}, 학과: {ctx.get('department') or '미정'}\n"
                f"  게시일: {ctx.get('posted_at')} / 마감: {ctx.get('deadline_at') or '미정'}"
            )
            blocks.append(block)
        return "\n\n".join(blocks)

    def _build_filters(
        self,
        department: Optional[str],
        grade: Optional[str],
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if department:
            filters["department"] = department
        if grade:
            filters["audience_grade"] = grade
        return filters

    def _build_regex_pattern(self, question: str) -> Optional[str]:
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", question)
        tokens = tokens[:5]
        if not tokens:
            stripped = question.strip()
            return re.escape(stripped) if stripped else None
        return "|".join(re.escape(token) for token in tokens)

    def _fallback_answer(self, contexts: Sequence[Dict[str, Any]]) -> str:
        lines = [
            "LLM 응답 생성을 사용할 수 없어 수집된 공지를 간단히 정리해 드릴게요:",
        ]
        for ctx in contexts:
            posted_at = ctx.get("posted_at", "")[:10] or "날짜 미정"
            summary = ctx.get("summary") or ctx.get("body_snippet") or ""
            department = ctx.get("department") or "학교"
            lines.append(
                f"- {ctx['title']} ({department}, {posted_at})\n"
                f"  주요 내용: {summary}"
            )
        lines.append("더 구체적인 내용이 필요하면 키워드를 조금 더 좁혀서 다시 질문해 주세요.")
        return "\n".join(lines)



    def _build_response(
        self,
        answer: str,
        citations: List[str],
        contexts: List[Dict[str, Any]],
        refused: bool,
        reason: str,
        question: str,
    ) -> Dict[str, Any]:
        return {
            "answer": answer,
            "citations": citations,
            "notices": contexts,
            "meta": {
                "question": question,
                "refused": refused,
                "reason": reason,
            },
        }

    def _normalize_question(self, question: str) -> str:
        return " ".join(question.strip().split())

    def _refusal_message_for_reason(self, reason: str, question: str) -> str:
        clean = question.strip()
        templates: Dict[str, Any] = {
            "empty_question": "질문이 비어 있어 답변을 드릴 수 없어요. 궁금한 내용을 입력해 주세요.",
            "out_of_scope": "해당 질문은 학교 공지 범위를 벗어나 안내해 드리기 어려워요.",
            "inappropriate": "부적절한 표현이 포함되어 있어 답변할 수 없어요.",
            "no_context": f"'{clean}'와 관련된 공지를 찾지 못해 답변을 드릴 수 없어요." if clean else "관련 공지를 찾지 못해 답변을 드릴 수 없어요.",
            "llm_unavailable": "답변을 생성하는 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.",
            "verification_failed": "공지 내용으로 답을 충분히 뒷받침할 수 없어 제공해 드릴 수 없어요.",
        }
        message = templates.get(reason)
        if message:
            return message
        return self.refusal_message

    def _guardrail_reason(self, question: str) -> Optional[str]:
        lowered = question.lower()
        for keyword in ABUSIVE_KEYWORDS:
            if keyword in question or keyword in lowered:
                return "inappropriate"
        for keyword in OUT_OF_SCOPE_KEYWORDS:
            if keyword in question or keyword in lowered:
                return "out_of_scope"
        return None

    def _truncate(self, text: str, limit: int) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3].rstrip()}..."
