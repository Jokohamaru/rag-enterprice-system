from __future__ import annotations

import json
import logging

from src.config.settings import Settings
from src.ingestion.chunkers.base import count_tokens
from src.llm.base import LLMMessage, LLMProvider
from src.schemas.chunk import ChunkRecord
from src.schemas.document import DocumentItem
from src.schemas.workspace import (
    NotebookOverviewResponse,
    SourceGuideResponse,
    StudioGenerateRequest,
    StudioGenerateResponse,
    StudioGenerateType,
)
from src.storage.workspace_store import WorkspaceStore
from src.vectordb.base import VectorStore

logger = logging.getLogger(__name__)

STUDIO_TITLES: dict[StudioGenerateType, str] = {
    "summary": "Tóm tắt tổng hợp nguồn tài liệu",
    "faq": "Câu hỏi thường gặp (FAQ)",
    "briefing": "Tài liệu tóm lược điều hành (Briefing Doc)",
    "study_guide": "Hướng dẫn nắm bắt & ôn tập",
    "comparison_table": "Bảng đối chiếu & tổng hợp quy định",
}

STUDIO_PROMPTS: dict[StudioGenerateType, str] = {
    "summary": (
        "Hãy viết bản **Tóm tắt tổng hợp** có cấu trúc rõ ràng (Tổng quan, Các điểm cốt lõi, Quy trình/Định mức quan trọng) "
        "từ các đoạn tài liệu bên dưới. Gắn mã nguồn [1], [2]... tương ứng."
    ),
    "faq": (
        "Hãy tạo danh sách **6–8 Câu hỏi thường gặp (FAQ)** kèm câu trả lời ngắn gọn, chính xác dựa trên các đoạn tài liệu. "
        "Mỗi câu trả lời cần gắn mã nguồn [1], [2]... tương ứng."
    ),
    "briefing": (
        "Hãy soạn một **Briefing Document** dành cho lãnh đạo/nhân sự mới gồm: Mục tiêu tài liệu, Các quy định & chỉ số quan trọng, "
        "Rủi ro/Lưu ý tuân thủ, và Hành động khuyến nghị. Gắn mã nguồn [1], [2]... tương ứng."
    ),
    "study_guide": (
        "Hãy tạo **Hướng dẫn học & ôn tập** gồm: Thuật ngữ/Khái niệm chính, Điểm cần nhớ theo chủ đề, và 5 câu hỏi tự kiểm tra kèm gợi ý đáp án ngắn. "
        "Gắn mã nguồn [1], [2]... tương ứng."
    ),
    "comparison_table": (
        "Hãy tổng hợp các quy định, quy trình hoặc hạng mục trong tài liệu thành **Bảng so sánh Markdown** rõ ràng (cột: Hạng mục, Quy định/Định mức, Điều kiện/Thời hạn, Nguồn), "
        "kèm nhận xét ngắn bên dưới. Gắn mã nguồn [1], [2]... tương ứng."
    ),
}


class StudioService:
    """NotebookLM-inspired AI tools: Source Guide, Notebook Overview, and Studio artifacts."""

    def __init__(
        self,
        *,
        settings: Settings,
        vector_store: VectorStore,
        llm_provider: LLMProvider,
        workspace_store: WorkspaceStore,
    ) -> None:
        self.settings = settings
        self.vector_store = vector_store
        self.llm_provider = llm_provider
        self.workspace_store = workspace_store

    def generate_source_guide(self, document_id: str) -> SourceGuideResponse | None:
        doc = self.vector_store.get_document(document_id)
        if doc is None:
            return None

        chunks = self.vector_store.get_document_chunks(document_id)
        sample_chunks = self._sample_evenly(chunks, max_items=10)
        topics_fallback = self._extract_section_topics(chunks)
        questions_fallback = [
            f"Nội dung chính của {doc.title} là gì?",
            *(f"Quy định chi tiết ở mục \"{t}\"?" for t in topics_fallback[:2]),
        ][:3]

        if not self.llm_provider.is_configured or not sample_chunks:
            summary = doc.summary or (sample_chunks[0].content[:320] + "..." if sample_chunks else "Tài liệu chưa có đoạn nội dung.")
            return SourceGuideResponse(
                document_id=doc.id,
                document_title=doc.title,
                summary=summary,
                key_topics=topics_fallback,
                suggested_questions=questions_fallback,
                chunk_count=len(chunks),
                generation_mode="extractive_fallback",
                model_used=self.llm_provider.model_name or None,
            )

        context_text = "\n\n".join(f"[{c.section}] {c.content[:550]}" for c in sample_chunks)
        prompt = (
            "Phân tích tài liệu sau và trả về JSON với 3 khóa:\n"
            '- "summary": tóm tắt 3-4 câu tiếng Việt súc tích\n'
            '- "keyTopics": mảng 3-5 chủ đề/từ khóa ngắn\n'
            '- "suggestedQuestions": mảng 3 câu hỏi hay nhất người đọc nên hỏi về tài liệu này\n\n'
            f"Tên tài liệu: {doc.title} ({doc.category})\n"
            f"Các đoạn tiêu biểu:\n{context_text}"
        )
        try:
            res = self.llm_provider.generate(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=700,
                json_mode=True,
            )
            data = json.loads(res.text)
            summary = str(data.get("summary") or doc.summary or "").strip()
            key_topics = [str(x).strip() for x in (data.get("keyTopics") or []) if str(x).strip()][:6]
            suggested = [str(x).strip() for x in (data.get("suggestedQuestions") or []) if str(x).strip()][:4]
            if summary:
                return SourceGuideResponse(
                    document_id=doc.id,
                    document_title=doc.title,
                    summary=summary,
                    key_topics=key_topics or topics_fallback,
                    suggested_questions=suggested or questions_fallback,
                    chunk_count=len(chunks),
                    generation_mode="llm",
                    model_used=res.model,
                )
        except Exception as exc:
            logger.warning("Source guide generation fallback for %s: %s", document_id, exc)

        summary = doc.summary or (sample_chunks[0].content[:320] + "...")
        return SourceGuideResponse(
            document_id=doc.id,
            document_title=doc.title,
            summary=summary,
            key_topics=topics_fallback,
            suggested_questions=questions_fallback,
            chunk_count=len(chunks),
            generation_mode="extractive_fallback",
            model_used=self.llm_provider.model_name or None,
        )

    def generate_overview(
        self,
        *,
        document_ids: list[str],
        notebook_id: str | None = None,
    ) -> NotebookOverviewResponse:
        docs = self._resolve_docs(document_ids)
        if not docs:
            return NotebookOverviewResponse(
                overview="Chưa có tài liệu nào được chọn để tạo tổng quan.",
                suggested_questions=[],
                generation_mode="extractive_fallback",
            )

        fallback_questions = [
            f"Tóm tắt những điểm quan trọng nhất từ {docs[0].title}?",
            *(f"Quy định chính trong tài liệu {d.title} là gì?" for d in docs[1:3]),
            "Các tài liệu hiện tại có điểm nào liên kết hoặc cần lưu ý đặc biệt không?",
        ][:4]

        if not self.llm_provider.is_configured:
            lines = [f"- **{d.title}** ({d.category}): {d.summary or 'Đã sẵn sàng tra cứu.'}" for d in docs[:6]]
            overview = "Tổng quan các nguồn tài liệu đang chọn:\n\n" + "\n".join(lines)
            if notebook_id:
                self.workspace_store.update_notebook(
                    notebook_id,
                    overview=overview,
                    suggested_questions=fallback_questions,
                )
            return NotebookOverviewResponse(
                overview=overview,
                suggested_questions=fallback_questions,
                model_used=self.llm_provider.model_name or None,
                generation_mode="extractive_fallback",
            )

        snippets = self._gather_representative_context(docs, max_chunks=14)
        prompt = (
            "Dựa trên danh sách tài liệu và trích đoạn sau, trả về JSON gồm 2 khóa:\n"
            '- "overview": đoạn tổng quan ngắn gọn 3-5 câu tiếng Việt mô tả bức tranh chung của tập tài liệu.\n'
            '- "suggestedQuestions": mảng đúng 4 câu hỏi tiếng Việt cụ thể, hữu ích mà người dùng có thể hỏi ngay.\n\n'
            f"Tài liệu:\n{snippets}"
        )
        try:
            res = self.llm_provider.generate(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.25,
                max_tokens=700,
                json_mode=True,
            )
            data = json.loads(res.text)
            overview = str(data.get("overview") or "").strip()
            suggested = [str(x).strip() for x in (data.get("suggestedQuestions") or []) if str(x).strip()][:4]
            if overview:
                final_questions = suggested or fallback_questions
                if notebook_id:
                    self.workspace_store.update_notebook(
                        notebook_id,
                        overview=overview,
                        suggested_questions=final_questions,
                    )
                return NotebookOverviewResponse(
                    overview=overview,
                    suggested_questions=final_questions,
                    model_used=res.model,
                    generation_mode="llm",
                )
        except Exception as exc:
            logger.warning("Notebook overview generation failed; using fallback: %s", exc)

        lines = [f"- **{d.title}** ({d.category}): {d.summary or 'Đã sẵn sàng tra cứu.'}" for d in docs[:6]]
        overview = "Tổng quan các nguồn tài liệu đang chọn:\n\n" + "\n".join(lines)
        return NotebookOverviewResponse(
            overview=overview,
            suggested_questions=fallback_questions,
            model_used=self.llm_provider.model_name or None,
            generation_mode="extractive_fallback",
        )

    def generate_studio_artifact(self, req: StudioGenerateRequest) -> StudioGenerateResponse:
        docs = self._resolve_docs(req.document_ids)
        base_title = STUDIO_TITLES[req.type]
        if not docs:
            return StudioGenerateResponse(
                title=base_title,
                content="Vui lòng bật ít nhất một tài liệu sẵn sàng để Studio tổng hợp nội dung.",
                type=req.type,
                generation_mode="extractive_fallback",
            )

        context = self._gather_representative_context(docs, max_chunks=18)
        title = f"{base_title} ({len(docs)} nguồn)"
        content = ""
        generation_mode: str = "extractive_fallback"
        model_used: str | None = self.llm_provider.model_name or None

        if self.llm_provider.is_configured and context:
            instruction = STUDIO_PROMPTS[req.type]
            if req.custom_instruction and req.custom_instruction.strip():
                instruction += f"\nYêu cầu bổ sung: {req.custom_instruction.strip()}"

            messages = [
                LLMMessage(
                    role="system",
                    content=(
                        "Bạn là NotebookLM Studio assistant. Chỉ sử dụng thông tin trong các trích đoạn nguồn, "
                        "trình bày bằng tiếng Việt Markdown sạch đẹp và gắn mã nguồn [1], [2]..."
                    ),
                ),
                LLMMessage(role="user", content=f"{instruction}\n\nNguồn tài liệu:\n{context}"),
            ]
            try:
                res = self.llm_provider.generate(
                    messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                if res.text.strip():
                    content = res.text.strip()
                    generation_mode = "llm"
                    model_used = res.model
            except Exception as exc:
                logger.warning("Studio artifact generation failed; using fallback: %s", exc)

        if not content:
            content = self._build_fallback_studio(docs, req.type)

        saved_note = None
        if req.save_as_note:
            saved_note = self.workspace_store.create_note(
                title=title,
                content=content,
                note_type=req.type,
                notebook_id=req.notebook_id,
                source_document_ids=[d.id for d in docs],
            )

        return StudioGenerateResponse(
            title=title,
            content=content,
            type=req.type,
            generation_mode=generation_mode,  # type: ignore[arg-type]
            model_used=model_used,
            note=saved_note,
        )

    def _resolve_docs(self, document_ids: list[str]) -> list[DocumentItem]:
        all_docs = [
            d
            for d in self.vector_store.list_documents(tenant_id=self.settings.default_tenant_id)
            if d.status == "ready"
        ]
        if document_ids:
            allowed = set(document_ids)
            return [d for d in all_docs if d.id in allowed]
        return [d for d in all_docs if d.enabled]

    def _gather_representative_context(self, docs: list[DocumentItem], *, max_chunks: int = 16) -> str:
        per_doc_limit = max(2, max_chunks // max(len(docs), 1))
        blocks: list[str] = []
        used_tokens = 0
        idx = 1
        for doc in docs:
            chunks = self.vector_store.get_document_chunks(doc.id)
            for chunk in self._sample_evenly(chunks, max_items=per_doc_limit):
                block = f"[{idx}] {doc.title} | {chunk.section}\n{chunk.content}"
                tok = count_tokens(block)
                if blocks and used_tokens + tok > self.settings.context_max_tokens:
                    return "\n\n---\n\n".join(blocks)
                blocks.append(block)
                used_tokens += tok
                idx += 1
        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _sample_evenly(chunks: list[ChunkRecord], *, max_items: int) -> list[ChunkRecord]:
        if len(chunks) <= max_items:
            return chunks
        step = len(chunks) / max_items
        return [chunks[int(i * step)] for i in range(max_items)]

    @staticmethod
    def _extract_section_topics(chunks: list[ChunkRecord]) -> list[str]:
        topics: list[str] = []
        seen: set[str] = set()
        for ch in chunks:
            sec = ch.section.strip()
            if sec and sec not in seen:
                seen.add(sec)
                topics.append(sec)
            if len(topics) >= 5:
                break
        return topics or ["Tổng quan tài liệu"]

    def _build_fallback_studio(self, docs: list[DocumentItem], artifact_type: StudioGenerateType) -> str:
        sections: list[str] = [f"### {STUDIO_TITLES[artifact_type]} (Chế độ trích xuất nhanh)\n"]
        for idx, doc in enumerate(docs[:6], start=1):
            chunks = self.vector_store.get_document_chunks(doc.id)
            excerpt = chunks[0].content[:280].strip() if chunks else doc.summary
            sections.append(f"- **{doc.title}** [{idx}] ({doc.category}): {excerpt}...")
        return "\n".join(sections)
