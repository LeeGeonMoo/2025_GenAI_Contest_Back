from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from beanie.operators import In
from beanie.exceptions import CollectionWasNotInitialized
from bson import ObjectId
from bson.errors import InvalidId

from app.clients.llm import LLMDisabledError, LLMRequestError
from app.models.conversation import Conversation, Message
from app.models.post import Post
from app.services import vector_store
from app.services.llm_service import LLMService
from app.db.mongo import init_db
from beanie.exceptions import CollectionWasNotInitialized

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "너는 대학 공지사항 전문 어시스턴트다. 항상 근거를 공지 데이터에서 찾고, 없으면 정중히 모른다고 답해라. "
    "모르면 상담/위로/추측 대신 '정보가 없습니다'라고 하라. "
    "답변은 한국어로, 두괄식 요약 → 세부 bullet/번호 리스트 순으로 짧게 정리하고, 마크다운/아이콘을 활용해 가독성을 높여라. "
    "링크는 본문에도 한 번 언급하고, JSON의 source_link에도 포함한다."
)

OUT_OF_SCOPE_KEYWORDS = [
    "주식",
    "환율",
    "로또",
    "날씨",
    "스포츠",
    "tour",
    "weather",
    "stock",
    "lotto",
    "kbo",
    "nba",
    "premier league",
]

ABUSIVE_KEYWORDS = [
    "fuck",
    "shit",
    "sex",
    "porn",
    "18",
    "개새",
    "씨발",
]


class ChatService:
    """
    Conversation-aware RAG chat (Mongo history + Qdrant contexts).
    Keeps last `history_limit` turns per session.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        refusal_message: str = "공지 데이터로는 답변이 어려워요.",
        max_candidates: int = 8,
        max_context_items: int = 4,
        history_limit: int = 10,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        self.refusal_message = refusal_message
        self.max_candidates = max_candidates
        self.max_context_items = max_context_items
        self.history_limit = history_limit

    async def answer(
        self,
        question: str,
        user_id: Optional[str] = None,
        department: Optional[str] = None,
        grade: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Ensure DB init; if unavailable in test/offline environments, continue with empty data.
        try:
            await self._ensure_db()
        except Exception:
            logger.warning("DB unavailable; proceeding without DB context.")
        normalized = self._normalize_question(question)
        conversation = await self._get_or_create_conversation(session_id, user_id)
        history = await self._load_history(conversation.id) if conversation else []

        if not normalized:
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._refusal_message_for_reason("empty_question", question),
                [],
                [],
                True,
                "empty_question",
            )

        guardrail_reason = self._guardrail_reason(normalized)
        if guardrail_reason:
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._refusal_message_for_reason(guardrail_reason, question),
                [],
                [],
                True,
                guardrail_reason,
            )

        if self._is_greeting(normalized):
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._greeting_message(),
                [],
                [],
                False,
                "greeting",
                source="system",
                intent="greeting",
            )
        if self._is_goodbye(normalized):
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._goodbye_message(),
                [],
                [],
                False,
                "goodbye",
                source="system",
                intent="goodbye",
            )

        intent = self._detect_intent(normalized, history, conversation)

        contexts: List[Dict[str, Any]] = []
        if intent == "followup":
            contexts = await self._followup_contexts(conversation, department, grade)
        if not contexts:
            contexts = await self._retrieve_contexts(
                normalized,
                department=department,
                grade=grade,
            )
        if not contexts:
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._refusal_message_for_reason("no_context", question),
                [],
                [],
                True,
                "no_context",
                intent=intent,
            )

        grounded = await self._generate_grounded_answer(normalized, contexts)
        if grounded is None:
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._refusal_message_for_reason("llm_unavailable", question),
                [],
                [],
                True,
                "llm_unavailable",
                intent=intent,
            )

        status = grounded.get("status", "success")
        if status == "no_info":
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._refusal_message_for_reason("no_context", question),
                [],
                [],
                True,
                "no_context",
                intent=intent,
            )
        if status == "fallback":
            return await self._respond_and_store(
                conversation,
                history,
                question,
                grounded.get("answer_md") or self._fallback_answer(contexts),
                grounded.get("citations") or [],
                contexts,
                False,
                "success",
                source_links=grounded.get("source_links", []),
                source=grounded.get("source", "fallback"),
                intent=intent,
            )

        answer_text = grounded.get("answer_md") or grounded.get("answer")
        citations = grounded.get("citations") or []
        norm_citations: List[Dict[str, Any]] = []
        for c in citations:
            if isinstance(c, dict):
                norm_citations.append(
                    {
                        "post_id": c.get("post_id") or c.get("id"),
                        "title": c.get("title"),
                        "link": c.get("link"),
                    }
                )
            else:
                norm_citations.append({"post_id": c, "title": None, "link": None})

        verified, reason = await self._verify_answer(
            normalized,
            answer_text or "",
            norm_citations,
            contexts,
        )
        if not verified:
            logger.info("Verification rejected answer: %s", reason)
            return await self._respond_and_store(
                conversation,
                history,
                question,
                self._refusal_message_for_reason("verification_failed", question),
                [],
                [],
                True,
                "verification_failed",
                intent=intent,
            )

        return await self._respond_and_store(
            conversation,
            history,
            question,
            answer_text or self._refusal_message_for_reason("llm_unavailable", question),
            norm_citations,
            contexts,
            False,
            "success",
            source_links=grounded.get("source_links", []),
            source=grounded.get("source", "llm"),
            intent=intent,
        )

    async def reset_session(self, session_id: str) -> bool:
        try:
            convo = await Conversation.get(session_id)
        except CollectionWasNotInitialized:
            return False
        if not convo:
            return False
        await Message.find(Message.conversation_id == str(convo.id)).delete()
        await convo.delete()
        return True

    # --------- History helpers ---------
    async def _get_or_create_conversation(
        self,
        session_id: Optional[str],
        user_id: Optional[str],
    ) -> Conversation:
        try:
            if session_id:
                # session_id가 ObjectId 형태가 아니면 새로운 세션을 생성한다.
                try:
                    ObjectId(session_id)
                    convo = await Conversation.get(session_id)
                    if convo:
                        return convo
                except (InvalidId, ValueError):
                    convo = None
            convo = Conversation(
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            await convo.insert()
            return convo
        except CollectionWasNotInitialized:
            return None

    async def _load_history(self, conversation_id: str) -> List[Dict[str, str]]:
        try:
            messages = (
                await Message.find(Message.conversation_id == str(conversation_id))
                .sort(-Message.created_at)
                .limit(self.history_limit)
                .to_list()
            )
            messages.reverse()
            return [{"role": msg.role, "content": msg.content} for msg in messages]
        except Exception:
            return []

    async def _append_history(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
    ) -> None:
        if conversation_id is None:
            return
        try:
            now = datetime.now(timezone.utc)
            await Message(
                conversation_id=str(conversation_id),
                role="user",
                content=user_content,
                created_at=now,
            ).insert()
            await Message(
                conversation_id=str(conversation_id),
                role="assistant",
                content=assistant_content,
                created_at=datetime.now(timezone.utc),
            ).insert()
            convo = await Conversation.get(conversation_id)
            if convo:
                await convo.update({"$set": {"updated_at": datetime.now(timezone.utc)}})

            count = await Message.find(Message.conversation_id == str(conversation_id)).count()
            max_allowed = self.history_limit * 2
            if count > max_allowed:
                excess = count - max_allowed
                old_msgs = (
                    await Message.find(Message.conversation_id == str(conversation_id))
                    .sort(Message.created_at)
                    .limit(excess)
                    .to_list()
                )
                for msg in old_msgs:
                    await msg.delete()
        except Exception:
            return

    # --------- Context retrieval ---------
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
        await self._ensure_db()
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

        posts = await Post.find(In("_id", mongo_ids)).to_list()
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
        await self._ensure_db()
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

    # --------- LLM answer generation ---------
    async def _generate_grounded_answer(
        self,
        question: str,
        contexts: Sequence[Dict[str, Any]],
        history: Optional[Sequence[Dict[str, str]]] = None,
    ) -> Optional[Dict[str, Any]]:
        context_block = self._render_context_block(contexts)
        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-self.history_limit :])
        user_content = (
            "사용자 질문:\n"
            f"{question}\n\n"
            "관련 공지들:\n"
            f"{context_block}\n\n"
            "규칙:\n"
            "- 공지 근거 없는 내용은 답하지 말 것\n"
            "- citations에는 post_id와 title을 포함\n"
            "- 답변은 마크다운 + 아이콘 사용, 링크는 본문에도 한 번 언급하고, source_link(JSON)에도 포함\n"
            "- 답변 길이: 400자 이하, 항목은 3~4개 이하로 짧게 요약\n"
            "- citations/목록은 최대 3건까지만 포함\n"
            'JSON 예시: {"answer": "...", "citations": [{"post_id":"...", "title":"...", "link":"..."}], "needs_more_context": false}'
        )
        messages.append({"role": "user", "content": user_content})
        try:
            content = await self.llm_service.client.chat_completion(
                messages=messages,
                max_tokens=900,
                temperature=0.2,
            )
        except (LLMDisabledError, LLMRequestError) as exc:
            logger.warning("LLM chat unavailable, fallback: %s", exc)
            return {
                "answer_md": self._fallback_answer(contexts),
                "citations": [{"post_id": ctx["post_id"], "title": ctx["title"], "link": ctx.get("source_link")} for ctx in contexts],
                "source": "fallback",
                "source_links": [ctx.get("source_link") for ctx in contexts if ctx.get("source_link")],
            }

        parsed = self._parse_llm_response(content, contexts)
        status = parsed.get("status")

        if status == "error":
            logger.warning("Failed to parse LLM chat response: %s", content)
            return {
                "status": "fallback",
                "answer_md": self._fallback_answer(contexts),
                "citations": [{"post_id": ctx["post_id"], "title": ctx["title"], "link": ctx.get("source_link")} for ctx in contexts],
                "source": "fallback",
                "source_links": [ctx.get("source_link") for ctx in contexts if ctx.get("source_link")],
            }
        if status == "no_info":
            return {"status": "no_info"}

        parsed["status"] = "success"
        parsed["source"] = "llm"
        return parsed

    def _parse_llm_response(
        self,
        raw: str,
        contexts: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not raw:
            return {"status": "error", "reason": "empty_raw"}
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"status": "error", "reason": "json_parse_error"}

        answer = (payload.get("answer") or "").strip()
        citations = payload.get("citations") or []
        needs_more = bool(payload.get("needs_more_context"))

        if not answer or needs_more:
            return {"status": "no_info"}

        valid_ids = {ctx["post_id"] for ctx in contexts}
        filtered = []
        links: List[str] = []
        for c in citations:
            if isinstance(c, dict):
                pid = c.get("post_id")
                title = c.get("title")
                link = c.get("link")
                if pid in valid_ids:
                    filtered.append({"post_id": pid, "title": title, "link": link})
                    if link:
                        links.append(link)
            else:
                if c in valid_ids:
                    filtered.append({"post_id": c, "title": None, "link": None})
        if not filtered:
            # 답변은 있으나 인용이 없으면 정보 부족으로 처리
            return {"status": "no_info"}
        return {"answer_md": answer, "citations": filtered, "source_links": links}

    async def _verify_answer(
        self,
        question: str,
        answer: str,
        citations: Sequence[Dict[str, Any]],
        contexts: Sequence[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        stripped_answer = answer.strip()
        if not stripped_answer:
            return False, "empty_answer"

        client = self.llm_service.client
        if not getattr(client, "chat_enabled", False):
            return True, "verification_skipped_chat_disabled"

        messages = [
            {"role": "system", "content": "답변이 공지 근거에 있는지 JSON으로 검증해줘."},
            {
                "role": "user",
                "content": (
                    f"질문:\n{question}\n\n"
                    f"답변:\n{stripped_answer}\n\n"
                    f"citations: {citations}\n"
                    'JSON으로 {"valid": true/false, "reason": "..."} 반환'
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

    # --------- Scoring ---------
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
        now = datetime.now(timezone.utc)
        posted_at = post.posted_at
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        delta_hours = max(0.0, (now - posted_at).total_seconds() / 3600)
        return max(0.1, 1 / (1 + delta_hours / 24))

    # --------- Formatting ---------
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
            "source_link": post.url,
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
                f"  본문 요약: {ctx.get('body_snippet')}\n"
                f"  대상 학년: {grades}, 학과: {ctx.get('department') or '전체'}\n"
                f"  게시일: {ctx.get('posted_at')} / 마감: {ctx.get('deadline_at') or '없음'}\n"
            )
            blocks.append(block)
        return "\n".join(blocks)

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
            "LLM 연결이 불안정해요. 대신 최근 공지를 요약해드릴게요 📌",
        ]
        for ctx in contexts:
            posted_at = ctx.get("posted_at", "")[:10] or "날짜 없음"
            summary = ctx.get("summary") or ctx.get("body_snippet") or ""
            department = ctx.get("department") or "학교"
            lines.append(
                f"- {ctx['title']} ({department}, {posted_at})\n"
                f"  주요 내용: {summary}"
            )
        lines.append("더 구체적으로 물어보면 정확도가 올라가요!")
        return "\n".join(lines)

    def _build_response(
        self,
        answer_md: str,
        citations: List[Dict[str, Any]],
        contexts: List[Dict[str, Any]],
        refused: bool,
        reason: str,
        question: str,
        session_id: str,
        source_links: Optional[List[str]] = None,
        source: str = "llm",
        intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        citation_ids = [
            c["post_id"] if isinstance(c, dict) else c
            for c in citations
        ]
        return {
            "answer_md": answer_md,
            "answer": answer_md,  # backward compatibility with existing clients/tests
            "citations": citation_ids,
            "citation_details": citations,
            "source_links": source_links or [],
            "notices": contexts,
            "meta": {
                "question": question,
                "refused": refused,
                "reason": reason,
                "session_id": session_id,
                "source": source,
                "intent": intent,
            },
        }

    def _normalize_question(self, question: str) -> str:
        return " ".join(question.strip().split())

    def _refusal_message_for_reason(self, reason: str, question: str) -> str:
        clean = question.strip()
        templates: Dict[str, Any] = {
            "empty_question": "질문이 비어 있어요. 구체적으로 다시 말씀해 주세요.",
            "out_of_scope": "공지 범위를 벗어난 질문이에요. 공지 관련 내용으로 다시 물어봐 주세요.",
            "inappropriate": "부적절한 표현이 있어 답변할 수 없습니다.",
            "no_context": f"'{clean}' 관련 공지를 찾지 못했어요. 키워드를 바꿔 다시 시도해 주세요." if clean else "관련 공지를 찾지 못했어요.",
            "llm_unavailable": "지금은 답변을 생성할 수 없어요. 잠시 후 다시 시도해 주세요.",
            "verification_failed": "답변 검증에 실패했어요. 조금 더 구체적으로 물어봐 주세요.",
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

    def _is_greeting(self, question: str) -> bool:
        greetings = {"안녕", "안녕하세요", "하이", "hi", "hello", "ㅎㅇ", "안녕하십니까"}
        return question.lower() in greetings

    def _greeting_message(self) -> str:
        return (
            "안녕하세요! 😊\n\n"
            "공지사항 기반 챗봇입니다. 궁금한 공지나 마감 일정을 물어보세요.\n"
            "- 예: 장학금 신청 마감 언제야?\n"
            "- 예: 인턴/채용 공지 뭐 있어?\n"
            "- 예: 특정 공지 링크/지원 자격 알려줘\n"
            "\n필요한 정보를 최대한 공지 근거와 함께 알려드릴게요!"
        )

    def _is_goodbye(self, question: str) -> bool:
        endings = {"잘가", "안녕히 계세요", "고마워", "수고했어", "바이", "goodbye", "bye"}
        q = question.lower()
        return any(q == e or q.endswith(e) for e in endings)

    def _goodbye_message(self) -> str:
        return (
            "대화를 종료할게요. 도움이 필요하면 언제든 다시 불러주세요! 🙌\n"
            "공지 마감/링크/지원 자격 등 궁금한 게 있으면 편하게 물어보세요."
        )

    def _detect_intent(self, question: str, history: Sequence[Dict[str, str]], conversation: Optional[Conversation]) -> str:
        lowered = question.lower()
        followup_triggers = ["그거", "그 공지", "거기", "그건", "지원 자격", "링크", "마감일", "언제까지", "자세히"]
        if conversation and conversation.last_citations:
            return "followup"
        if any(t in lowered for t in followup_triggers):
            return "followup"
        return "search"

    async def _followup_contexts(
        self,
        conversation: Optional[Conversation],
        department: Optional[str],
        grade: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not conversation or not conversation.last_citations:
            return []
        ids = [cid for cid in conversation.last_citations if cid]
        if not ids:
            return []
        posts = await Post.find(In("_id", [ObjectId(cid) for cid in ids if ObjectId.is_valid(cid)])).to_list()
        contexts: List[Dict[str, Any]] = []
        for post in posts:
            contexts.append(self._format_context(post, score=0.5, signals={"followup": True}))
        return contexts

    async def _ensure_db(self) -> None:
        try:
            Post.get_settings()
        except CollectionWasNotInitialized:
            try:
                await init_db()
            except Exception as exc:  # pragma: no cover - env without mongo
                logger.warning("DB init failed or unavailable: %s", exc)
                raise

    async def _respond_and_store(
        self,
        conversation: Conversation,
        history: List[Dict[str, str]],
        question: str,
        answer_md: str,
        citations: List[Dict[str, Any]],
        contexts: List[Dict[str, Any]],
        refused: bool,
        reason: str,
        source_links: Optional[List[str]] = None,
        source: str = "llm",
        intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._append_history(str(conversation.id) if conversation else None, question, answer_md)
        if conversation:
            try:
                await conversation.update(
                    {
                        "$set": {
                            "last_query": question,
                            "last_intent": intent,
                            "last_citations": [
                                c["post_id"] if isinstance(c, dict) else c for c in citations
                            ],
                            "updated_at": datetime.now(timezone.utc),
                        }
                    }
                )
            except Exception:
                pass
        return self._build_response(
            answer_md=answer_md,
            citations=citations,
            contexts=contexts,
            refused=refused,
            reason=reason,
            question=question,
            session_id=str(conversation.id) if conversation else "",
            source_links=source_links,
            source=source,
            intent=intent,
        )
