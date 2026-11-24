from __future__ import annotations

import logging
import uuid
from typing import Literal

from src.ingestion.chunkers.base import ChunkDraft
from src.schemas.chunk import ChunkRecord
from src.schemas.document import MetadataAttributes

logger = logging.getLogger(__name__)


def _extract_highlight(content: str, max_len: int = 120) -> str:
    clean = " ".join(content.split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rsplit(" ", 1)[0] + "..."


class ChunkEnricher:
    """Attach authorization metadata and Contextual Retrieval headers/summaries."""

    def __init__(
        self,
        *,
        contextual_mode: Literal["header", "llm"] = "header",
        gemini_api_key: str = "",
        gemini_context_model: str = "gemini-2.0-flash",
    ) -> None:
        self.contextual_mode = contextual_mode
        self.gemini_api_key = gemini_api_key.strip()
        self.gemini_context_model = gemini_context_model
        self._genai_client = None

    def enrich(
        self,
        drafts: list[ChunkDraft],
        *,
        meta: MetadataAttributes,
        doc_summary: str = "",
        enabled: bool = True,
    ) -> list[ChunkRecord]:
        records: list[ChunkRecord] = []
        for draft in drafts:
            chunk_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{meta.document_id}:{meta.content_hash}:{draft.chunk_index}",
                )
            )
            header = self._build_header_prefix(meta=meta, draft=draft)
            if self.contextual_mode == "llm" and self.gemini_api_key:
                llm_ctx = self._generate_llm_context(
                    doc_title=meta.title,
                    doc_summary=doc_summary,
                    section=draft.section,
                    chunk_text=draft.content,
                )
                contextual_content = f"{header}\n{llm_ctx}\n{draft.content}" if llm_ctx else f"{header}\n{draft.content}"
            else:
                contextual_content = f"{header}\n{draft.content}"

            records.append(
                ChunkRecord(
                    id=chunk_id,
                    document_id=meta.document_id,
                    document_title=meta.title,
                    category=meta.category,
                    section=draft.section,
                    page=draft.page,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    contextual_content=contextual_content,
                    highlight=_extract_highlight(draft.content),
                    parent_id=draft.parent_id,
                    token_count=draft.token_count,
                    tenant_id=meta.tenant_id,
                    department=meta.department,
                    access_groups=list(meta.access_groups),
                    enabled=enabled,
                    content_hash=meta.content_hash,
                )
            )
        return records

    @staticmethod
    def _build_header_prefix(*, meta: MetadataAttributes, draft: ChunkDraft) -> str:
        page_label = str(draft.page) if draft.page is not None else "N/A"
        return (
            f"[Tài liệu: {meta.title} | Danh mục: {meta.category} | "
            f"Phòng ban: {meta.department} | Mục: {draft.section} | Trang: {page_label}]"
        )

    def _generate_llm_context(
        self,
        *,
        doc_title: str,
        doc_summary: str,
        section: str,
        chunk_text: str,
    ) -> str:
        try:
            if self._genai_client is None:
                from google import genai

                self._genai_client = genai.Client(api_key=self.gemini_api_key)

            prompt = (
                "Viết 1-2 câu ngắn gọn (bằng ngôn ngữ của đoạn văn) giải thích bối cảnh của đoạn trích "
                "sau trong toàn bộ tài liệu để cải thiện độ chính xác tìm kiếm.\n"
                f"Tài liệu: {doc_title}\n"
                f"Tóm tắt: {doc_summary}\n"
                f"Mục: {section}\n"
                f"Đoạn trích:\n{chunk_text[:1500]}"
            )
            resp = self._genai_client.models.generate_content(
                model=self.gemini_context_model,
                contents=prompt,
            )
            return (resp.text or "").strip()
        except Exception as exc:
            logger.warning("LLM contextual summary fallback to header mode: %s", exc)
            return ""
