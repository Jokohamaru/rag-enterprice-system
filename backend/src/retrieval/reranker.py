from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from src.config.settings import Settings
from src.ingestion.sparse_indexer import tokenize_for_bm25
from src.llm.base import LLMMessage, LLMProvider
from src.schemas.chunk import ChunkRecord

logger = logging.getLogger(__name__)


@dataclass
class RerankCandidate:
    chunk: ChunkRecord
    rrf_score: float
    dense_score: float | None = None
    rerank_score: float = 0.0


class BaseReranker:
    def rerank(self, query: str, candidates: list[RerankCandidate], *, top_k: int) -> list[RerankCandidate]:
        raise NotImplementedError


class NoOpReranker(BaseReranker):
    def rerank(self, query: str, candidates: list[RerankCandidate], *, top_k: int) -> list[RerankCandidate]:
        out = sorted(candidates, key=lambda c: c.rrf_score, reverse=True)[:top_k]
        max_rrf = max((c.rrf_score for c in out), default=1.0) or 1.0
        for item in out:
            item.rerank_score = item.rrf_score / max_rrf
        return out


class LexicalOverlapReranker(BaseReranker):
    """Fast deterministic cross-signal reranker combining RRF, Vietnamese token overlap, and section match."""

    def rerank(self, query: str, candidates: list[RerankCandidate], *, top_k: int) -> list[RerankCandidate]:
        if not candidates:
            return []

        q_tokens = [tok for tok in tokenize_for_bm25(query) if len(tok) > 1]
        q_set = set(q_tokens)
        q_lower = " ".join(query.lower().split())
        max_rrf = max((c.rrf_score for c in candidates), default=1.0) or 1.0

        scored: list[RerankCandidate] = []
        for cand in candidates:
            rrf_norm = cand.rrf_score / max_rrf
            dense_norm = max(0.0, min(1.0, cand.dense_score)) if cand.dense_score is not None else rrf_norm

            if q_set:
                body_tokens = set(tokenize_for_bm25(cand.chunk.content))
                meta_tokens = set(tokenize_for_bm25(f"{cand.chunk.document_title} {cand.chunk.section}"))
                body_overlap = len(q_set.intersection(body_tokens)) / len(q_set)
                meta_overlap = len(q_set.intersection(meta_tokens)) / len(q_set)
            else:
                body_overlap = 0.0
                meta_overlap = 0.0

            phrase_bonus = 0.12 if (len(q_lower) >= 6 and q_lower in cand.chunk.content.lower()) else 0.0
            combined = 0.45 * rrf_norm + 0.25 * dense_norm + 0.22 * body_overlap + 0.08 * meta_overlap + phrase_bonus
            cand.rerank_score = round(min(1.0, max(0.0, combined)), 4)
            scored.append(cand)

        scored.sort(key=lambda c: c.rerank_score, reverse=True)
        return scored[:top_k]


class LLMReranker(BaseReranker):
    """LLM-as-Reranker scoring candidate relevance 0-10 in JSON with lexical fallback."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider
        self._fallback = LexicalOverlapReranker()

    def rerank(self, query: str, candidates: list[RerankCandidate], *, top_k: int) -> list[RerankCandidate]:
        if not candidates:
            return []
        if not self.llm_provider.is_configured or len(candidates) <= 1:
            return self._fallback.rerank(query, candidates, top_k=top_k)

        pool = candidates[: min(15, len(candidates))]
        numbered_blocks = [
            f"[{idx}] {c.chunk.document_title} | {c.chunk.section}: {c.chunk.content[:450]}"
            for idx, c in enumerate(pool)
        ]
        prompt = (
            "Chấm điểm mức độ liên quan (0 đến 10) của từng đoạn tài liệu đối với câu hỏi.\n"
            "Trả về JSON dạng {\"scores\": [s0, s1, ...]} đúng theo thứ tự index.\n\n"
            f"Câu hỏi: {query}\n\n"
            + "\n\n".join(numbered_blocks)
        )

        try:
            resp = self.llm_provider.generate(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.0,
                max_tokens=256,
                json_mode=True,
            )
            parsed = json.loads(resp.text)
            scores = parsed.get("scores")
            if isinstance(scores, list) and len(scores) == len(pool):
                for cand, raw_score in zip(pool, scores):
                    cand.rerank_score = round(max(0.0, min(1.0, float(raw_score) / 10.0)), 4)
                ranked = sorted(pool, key=lambda c: c.rerank_score, reverse=True)
                return ranked[:top_k]
        except Exception as exc:
            logger.warning("LLM reranker failed; falling back to lexical reranker: %s", exc)

        return self._fallback.rerank(query, candidates, top_k=top_k)


def build_reranker(settings: Settings, llm_provider: LLMProvider) -> BaseReranker:
    if settings.reranker_provider == "none":
        return NoOpReranker()
    if settings.reranker_provider == "llm":
        return LLMReranker(llm_provider)
    return LexicalOverlapReranker()
