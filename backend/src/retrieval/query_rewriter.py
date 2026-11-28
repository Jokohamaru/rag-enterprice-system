from __future__ import annotations

import logging

from src.llm.base import LLMMessage, LLMProvider
from src.schemas.query import ChatTurn

logger = logging.getLogger(__name__)


class QueryRewriter:
    """Rewrite follow-up conversational turns into standalone retrieval queries."""

    def __init__(self, llm_provider: LLMProvider, *, enabled: bool = True) -> None:
        self.llm_provider = llm_provider
        self.enabled = enabled

    def rewrite(self, question: str, history: list[ChatTurn]) -> str:
        clean_question = question.strip()
        if not self.enabled or not history or not self.llm_provider.is_configured:
            return clean_question

        recent_turns = history[-6:]
        transcript = "\n".join(
            f"{'Người dùng' if turn.role == 'user' else 'Trợ lý'}: {turn.content.strip()[:500]}"
            for turn in recent_turns
            if turn.content.strip()
        )
        if not transcript:
            return clean_question

        messages = [
            LLMMessage(
                role="system",
                content=(
                    "Bạn là bộ viết lại truy vấn tìm kiếm tài liệu. Dựa vào lịch sử hội thoại và câu hỏi mới nhất, "
                    "hãy viết lại câu hỏi mới nhất thành MỘT câu truy vấn độc lập, đầy đủ ngữ cảnh và từ khóa, "
                    "giữ nguyên ngôn ngữ của người dùng (mặc định tiếng Việt). "
                    "Chỉ trả về đúng câu truy vấn đã viết lại, không giải thích thêm."
                ),
            ),
            LLMMessage(
                role="user",
                content=f"Lịch sử gần đây:\n{transcript}\n\nCâu hỏi mới nhất: {clean_question}",
            ),
        ]

        try:
            result = self.llm_provider.generate(messages, temperature=0.0, max_tokens=160)
            rewritten = result.text.strip().strip('"').strip("'")
            if rewritten and len(rewritten) <= 400:
                return rewritten
        except Exception as exc:
            logger.warning("Query rewrite failed; using original question: %s", exc)

        return clean_question
