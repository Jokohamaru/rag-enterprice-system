from __future__ import annotations

import uuid

from src.ingestion.chunkers.base import BaseChunker, ChunkDraft, ChunkingOutput, count_tokens
from src.ingestion.chunkers.recursive import split_text_recursively
from src.schemas.chunk import ExtractedDocument, ParentChunk


class ParentChildChunker(BaseChunker):
    """Small-to-Big indexing: index fine child chunks linked to rich parent context chunks."""

    def __init__(
        self,
        *,
        parent_chunk_size: int = 1000,
        parent_chunk_overlap: int = 100,
        child_chunk_size: int = 250,
        child_chunk_overlap: int = 50,
    ) -> None:
        self.parent_chunk_size = parent_chunk_size
        self.parent_chunk_overlap = parent_chunk_overlap
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap

    def chunk(
        self,
        doc: ExtractedDocument,
        *,
        document_id: str,
        tenant_id: str,
        department: str,
    ) -> ChunkingOutput:
        parents: list[ParentChunk] = []
        children: list[ChunkDraft] = []
        parent_idx = 0
        child_idx = 0

        for page in doc.pages:
            parent_texts = split_text_recursively(
                page.text,
                chunk_size=self.parent_chunk_size,
                chunk_overlap=self.parent_chunk_overlap,
            )
            for p_text in parent_texts:
                parent_idx += 1
                parent_id = str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:parent:{parent_idx}:{p_text[:64]}")
                )
                parents.append(
                    ParentChunk(
                        parent_id=parent_id,
                        document_id=document_id,
                        tenant_id=tenant_id,
                        department=department,
                        section=page.section,
                        page=page.page_number,
                        chunk_index=parent_idx,
                        content=p_text,
                        token_count=count_tokens(p_text),
                    )
                )

                child_texts = split_text_recursively(
                    p_text,
                    chunk_size=self.child_chunk_size,
                    chunk_overlap=self.child_chunk_overlap,
                )
                for c_text in child_texts:
                    child_idx += 1
                    children.append(
                        ChunkDraft(
                            content=c_text,
                            page=page.page_number,
                            section=page.section,
                            chunk_index=child_idx,
                            token_count=count_tokens(c_text),
                            parent_id=parent_id,
                        )
                    )

        return ChunkingOutput(chunks=children, parent_chunks=parents)
