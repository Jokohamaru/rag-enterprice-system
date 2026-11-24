from __future__ import annotations

import re

import numpy as np

from src.ingestion.chunkers.base import BaseChunker, ChunkDraft, ChunkingOutput, count_tokens
from src.ingestion.chunkers.recursive import split_text_recursively
from src.ingestion.embedders.base import EmbeddingProvider
from src.schemas.chunk import ExtractedDocument

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


class SemanticChunker(BaseChunker):
    """Split narrative text at semantic similarity breakpoints between consecutive sentences."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        *,
        breakpoint_percentile: float = 20.0,
        max_chunk_tokens: int = 500,
    ) -> None:
        self.embedder = embedder
        self.breakpoint_percentile = breakpoint_percentile
        self.max_chunk_tokens = max_chunk_tokens

    def chunk(
        self,
        doc: ExtractedDocument,
        *,
        document_id: str,
        tenant_id: str,
        department: str,
    ) -> ChunkingOutput:
        drafts: list[ChunkDraft] = []
        chunk_idx = 0

        for page in doc.pages:
            sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(page.text) if s.strip()]
            if len(sentences) <= 2:
                for seg in split_text_recursively(page.text, chunk_size=self.max_chunk_tokens, chunk_overlap=40):
                    chunk_idx += 1
                    drafts.append(
                        ChunkDraft(
                            content=seg,
                            page=page.page_number,
                            section=page.section,
                            chunk_index=chunk_idx,
                            token_count=count_tokens(seg),
                        )
                    )
                continue

            # Batch-embed all sentences on the page at once
            vecs = np.asarray(
                self.embedder.embed_texts(sentences, task_type="SEMANTIC_SIMILARITY"),
                dtype=np.float32,
            )
            sims = [float(np.dot(vecs[i], vecs[i + 1])) for i in range(len(sentences) - 1)]
            threshold = float(np.percentile(sims, self.breakpoint_percentile)) if sims else 0.0

            grouped_texts = self._group_sentences(sentences, sims, threshold)
            for grp in grouped_texts:
                for seg in split_text_recursively(grp, chunk_size=self.max_chunk_tokens, chunk_overlap=40):
                    chunk_idx += 1
                    drafts.append(
                        ChunkDraft(
                            content=seg,
                            page=page.page_number,
                            section=page.section,
                            chunk_index=chunk_idx,
                            token_count=count_tokens(seg),
                        )
                    )

        return ChunkingOutput(chunks=drafts)

    def _group_sentences(
        self,
        sentences: list[str],
        sims: list[float],
        threshold: float,
    ) -> list[str]:
        groups: list[list[str]] = [[sentences[0]]]
        for i, sim in enumerate(sims):
            next_sent = sentences[i + 1]
            cur_tokens = count_tokens(" ".join(groups[-1]))
            next_tokens = count_tokens(next_sent)
            should_break = sim < threshold or (cur_tokens + next_tokens > self.max_chunk_tokens)
            if should_break:
                # 1-sentence overlap bridge when the previous group has >1 sentence
                bridge = [groups[-1][-1]] if len(groups[-1]) > 1 and next_tokens < self.max_chunk_tokens // 2 else []
                groups.append([*bridge, next_sent])
            else:
                groups[-1].append(next_sent)
        return [" ".join(g).strip() for g in groups if g]
