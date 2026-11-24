from __future__ import annotations

from src.ingestion.chunkers.base import BaseChunker, ChunkDraft, ChunkingOutput, count_tokens
from src.schemas.chunk import ExtractedDocument

DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", "")


def split_text_recursively(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[str]:
    """Split text hierarchically along natural boundaries while respecting token budget & overlap."""
    text = text.strip()
    if not text:
        return []
    if count_tokens(text) <= chunk_size:
        return [text]

    raw_pieces = _recursive_split(text, chunk_size=chunk_size, separators=separators)
    return _merge_pieces_with_overlap(raw_pieces, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _recursive_split(text: str, *, chunk_size: int, separators: tuple[str, ...]) -> list[str]:
    if count_tokens(text) <= chunk_size:
        return [text]

    if not separators:
        # Hard character slice as final safety guard
        step = max(80, chunk_size * 3)
        return [text[i : i + step].strip() for i in range(0, len(text), step) if text[i : i + step].strip()]

    sep = separators[0]
    rest_seps = separators[1:]

    if sep == "":
        parts = [text[i : i + max(80, chunk_size * 3)] for i in range(0, len(text), max(80, chunk_size * 3))]
    elif sep in text:
        raw_splits = text.split(sep)
        # Re-attach punctuation separator to keep sentences natural
        if sep in (". ", "? ", "! ", "; ", ", "):
            parts = [
                (p + sep.rstrip()).strip() if idx < len(raw_splits) - 1 else p.strip()
                for idx, p in enumerate(raw_splits)
                if p.strip()
            ]
        else:
            parts = [p.strip() for p in raw_splits if p.strip()]
    else:
        return _recursive_split(text, chunk_size=chunk_size, separators=rest_seps)

    result: list[str] = []
    for part in parts:
        if count_tokens(part) <= chunk_size:
            result.append(part)
        else:
            result.extend(_recursive_split(part, chunk_size=chunk_size, separators=rest_seps))
    return result


def _merge_pieces_with_overlap(pieces: list[str], *, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for piece in pieces:
        piece_tokens = count_tokens(piece)
        if current and current_tokens + piece_tokens > chunk_size:
            chunks.append(" ".join(current).strip())
            # Build trailing overlap buffer from the tail of `current`
            overlap_buf: list[str] = []
            overlap_tokens = 0
            if chunk_overlap > 0:
                for prev in reversed(current):
                    prev_toks = count_tokens(prev)
                    if overlap_tokens + prev_toks > chunk_overlap and overlap_buf:
                        break
                    if prev_toks <= chunk_overlap or not overlap_buf:
                        overlap_buf.insert(0, prev)
                        overlap_tokens += prev_toks
                    if overlap_tokens >= chunk_overlap:
                        break
            current = overlap_buf
            current_tokens = sum(count_tokens(x) for x in current)

        current.append(piece)
        current_tokens += piece_tokens

    if current:
        tail = " ".join(current).strip()
        if tail and (not chunks or tail != chunks[-1]):
            chunks.append(tail)

    return chunks


class RecursiveChunker(BaseChunker):
    """Default chunking strategy: recursive natural-boundary split with token overlap."""

    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 80) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly smaller than chunk_size.")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        doc: ExtractedDocument,
        *,
        document_id: str,
        tenant_id: str,
        department: str,
    ) -> ChunkingOutput:
        drafts: list[ChunkDraft] = []
        idx = 0
        for page in doc.pages:
            segments = split_text_recursively(
                page.text,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            for seg in segments:
                idx += 1
                drafts.append(
                    ChunkDraft(
                        content=seg,
                        page=page.page_number,
                        section=page.section,
                        chunk_index=idx,
                        token_count=count_tokens(seg),
                    )
                )
        return ChunkingOutput(chunks=drafts)
