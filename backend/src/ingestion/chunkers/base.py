from __future__ import annotations

import re
from abc import ABC, abstractmethod
from functools import lru_cache

from pydantic import BaseModel, Field

from src.schemas.chunk import ExtractedDocument, ParentChunk

FALLBACK_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@lru_cache(maxsize=1)
def _get_tiktoken_encoding():
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        # Trigger BPE cache check once so offline environments fall back cleanly
        enc.encode("test")
        return enc
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken `cl100k_base` with offline regex fallback."""
    if not text:
        return 0
    enc = _get_tiktoken_encoding()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(FALLBACK_TOKEN_RE.findall(text)))


class ChunkDraft(BaseModel):
    """Pre-enrichment chunk produced by a chunking strategy."""

    content: str
    page: int | None = None
    section: str = "Tổng quan"
    chunk_index: int
    token_count: int
    parent_id: str | None = None


class ChunkingOutput(BaseModel):
    """Unified output of any chunker, optionally including parent chunks."""

    chunks: list[ChunkDraft] = Field(default_factory=list)
    parent_chunks: list[ParentChunk] = Field(default_factory=list)


class BaseChunker(ABC):
    """Abstract text-splitting strategy interface."""

    @abstractmethod
    def chunk(
        self,
        doc: ExtractedDocument,
        *,
        document_id: str,
        tenant_id: str,
        department: str,
    ) -> ChunkingOutput:
        raise NotImplementedError
