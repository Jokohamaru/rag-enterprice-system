from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from src.config.settings import Settings
from src.ingestion.chunkers.base import count_tokens
from src.ingestion.embedders.base import EmbeddingProvider
from src.ingestion.sparse_indexer import SparseBM25Index, tokenize_for_bm25
from src.llm.base import LLMMessage, LLMProvider
from src.llm.factory import build_llm_provider
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.reranker import BaseReranker, RerankCandidate, build_reranker
from src.schemas.chunk import ChunkRecord, SearchFilter
from src.schemas.document import utc_now_iso
from src.schemas.query import ChatTurn, CitationItem, QueryRequest, QueryResponse
from src.schemas.workspace import ConversationMessage
from src.storage.workspace_store import WorkspaceStore
from src.vectordb.base import VectorStore

logger = logging.getLogger(__name__)

EMPTY_SCOPE_ANSWER = (
    "Hiện chưa có tài liệu nào được bật trong phạm vi tra cứu. "
    "Vui lòng bật ít nhất một tài liệu ở thanh bên trái hoặc tải thêm tài liệu vào Thư viện."
)

NO_MATCH_ANSWER = (
    "Không tìm thấy đoạn tài liệu phù hợp trong phạm vi đang chọn. "
    "Hãy thử diễn đạt lại câu hỏi hoặc mở rộng danh mục tài liệu ở thanh bên trái."
)

FOLLOW_UP_DELIMITER = "<<<FOLLOW_UPS>>>"
CITATION_REF_RE = re.compile(r"\[(\d+)\]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。\n])\s+")

SYSTEM_PROMPT = (
    "Bạn là trợ lý nghiên cứu tài liệu doanh nghiệp theo phong cách NotebookLM. "
    "Hãy trả lời câu hỏi của người dùng CHỈ dựa trên các đoạn trích dẫn tài liệu được cung cấp.\n\n"
    "Quy tắc bắt buộc:\n"
    "1. Trả lời bằng tiếng Việt rõ ràng, mạch lạc, có cấu trúc Markdown dễ đọc (dùng tiêu đề nhỏ, gạch đầu dòng, "
    "**in đậm** ý chính hoặc bảng Markdown khi so sánh).\n"
    "2. Gắn số trích dẫn dạng [1], [2]... ngay sau mỗi thông tin lấy từ đoạn tương ứng. Không tự bịa số trích dẫn.\n"
    "3. Tuyệt đối không suy diễn hoặc bịa đặt thông tin không có trong ngữ cảnh. Nếu thiếu dữ liệu, hãy nói rõ phần nào tài liệu chưa đề cập.\n"
    "4. Ở cuối câu trả lời, xuất đúng 3 câu hỏi gợi ý tiếp theo ngắn gọn liên quan trực tiếp đến tài liệu, "
    f"theo định dạng sau dòng phân tách {FOLLOW_UP_DELIMITER}:\n"
    f"{FOLLOW_UP_DELIMITER}\n"
    "- Câu hỏi gợi ý 1?\n"
    "- Câu hỏi gợi ý 2?\n"
    "- Câu hỏi gợi ý 3?"
)


@dataclass
class _PreparedRetrieval:
    question: str
    search_query: str
    rewritten_query: str | None
    history: list[ChatTurn]
    citations: list[CitationItem]
    context_blocks: list[str]
    early_answer: str | None = None


def _extract_query_highlight(content: str, query: str, fallback: str | None = None, max_len: int = 160) -> str | None:
    """Pick the sentence or snippet in `content` that best overlaps with `query` tokens."""
    clean_content = " ".join(content.split())
    if not clean_content:
        return fallback

    q_tokens = {tok for tok in tokenize_for_bm25(query) if len(tok) > 1}
    if not q_tokens:
        return fallback

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(content) if s.strip()]
    best_sentence = ""
    best_score = 0
    for sent in sentences:
        s_tokens = set(tokenize_for_bm25(sent))
        overlap = len(q_tokens.intersection(s_tokens))
        if overlap > best_score:
            best_score = overlap
            best_sentence = " ".join(sent.split())

    if best_score > 0 and best_sentence:
        if len(best_sentence) <= max_len:
            return best_sentence
        return best_sentence[: max_len - 3].rsplit(" ", 1)[0] + "..."
    return fallback


def _parse_answer_and_followups(raw_text: str) -> tuple[str, list[str]]:
    if FOLLOW_UP_DELIMITER not in raw_text:
        return raw_text.strip(), []

    answer_part, tail = raw_text.split(FOLLOW_UP_DELIMITER, 1)
    follow_ups: list[str] = []
    for line in tail.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if cleaned:
            follow_ups.append(cleaned)
    return answer_part.strip(), follow_ups[:3]


def _mark_used_citations(answer: str, citations: list[CitationItem]) -> list[CitationItem]:
    referenced = {int(m.group(1)) for m in CITATION_REF_RE.finditer(answer)}
    if not referenced:
        return citations
    return [
        cit.model_copy(update={"used_in_answer": cit.citation_number in referenced})
        for cit in citations
    ]


class RAGQueryService:
    """Hybrid Search (Vector + BM25 via RRF), Query Rewriting, Reranking, Small-to-Big expansion, and Grounded LLM."""

    def __init__(
        self,
        *,
        settings: Settings,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        bm25_index: SparseBM25Index,
        llm_provider: LLMProvider | None = None,
        reranker: BaseReranker | None = None,
        workspace_store: WorkspaceStore | None = None,
    ) -> None:
        self.settings = settings
        self.vector_store = vector_store
        self.embedder = embedder
        self.bm25_index = bm25_index
        self.llm_provider = llm_provider or build_llm_provider(settings)
        self.reranker = reranker or build_reranker(settings, self.llm_provider)
        self.query_rewriter = QueryRewriter(self.llm_provider, enabled=settings.query_rewrite_enabled)
        self.workspace_store = workspace_store

    def query(self, req: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        prepared = self._prepare_retrieval(req)

        if prepared.early_answer is not None:
            response = QueryResponse(
                answer=prepared.early_answer,
                citations=[],
                latency_ms=self._elapsed_ms(started),
                generation_mode="extractive_fallback",
                rewritten_query=prepared.rewritten_query,
                conversation_id=req.conversation_id,
            )
            self._persist_turn(req, response)
            return response

        answer, generation_mode, model_used, provider_used, follow_ups, warning = self._generate_answer(
            question=prepared.question,
            history=prepared.history,
            context_blocks=prepared.context_blocks,
            citations=prepared.citations,
        )
        updated_citations = _mark_used_citations(answer, prepared.citations)
        response = QueryResponse(
            answer=answer,
            citations=updated_citations,
            latency_ms=self._elapsed_ms(started),
            generation_mode=generation_mode,
            model_used=model_used,
            provider_used=provider_used,
            rewritten_query=prepared.rewritten_query,
            follow_up_questions=follow_ups,
            warning=warning,
            conversation_id=req.conversation_id,
        )
        self._persist_turn(req, response)
        return response

    def stream_query(self, req: QueryRequest) -> Iterator[dict]:
        """Yield SSE-ready event dictionaries (`status`, `citations`, `delta`, `done`)."""
        started = time.perf_counter()
        yield {"event": "status", "data": {"stage": "analyzing", "message": "Đang phân tích câu hỏi và phạm vi nguồn..."}}

        try:
            prepared = self._prepare_retrieval(req)
        except ValueError as exc:
            yield {"event": "error", "data": {"detail": str(exc)}}
            return

        if prepared.early_answer is not None:
            yield {"event": "citations", "data": {"citations": []}}
            yield {"event": "delta", "data": {"text": prepared.early_answer}}
            response = QueryResponse(
                answer=prepared.early_answer,
                citations=[],
                latency_ms=self._elapsed_ms(started),
                generation_mode="extractive_fallback",
                rewritten_query=prepared.rewritten_query,
                conversation_id=req.conversation_id,
            )
            self._persist_turn(req, response)
            yield {"event": "done", "data": response.model_dump(mode="json", by_alias=True)}
            return

        yield {
            "event": "status",
            "data": {
                "stage": "retrieving",
                "message": f"Đã tìm thấy {len(prepared.citations)} đoạn liên quan. Đang tổng hợp câu trả lời...",
            },
        }
        yield {
            "event": "citations",
            "data": {
                "citations": [c.model_dump(mode="json", by_alias=True) for c in prepared.citations],
            },
        }

        if self.llm_provider.is_configured:
            messages = self._build_llm_messages(
                question=prepared.question,
                history=prepared.history,
                context_blocks=prepared.context_blocks,
            )
            try:
                raw_chunks: list[str] = []
                pending = ""
                delimiter_seen = False
                guard_len = len(FOLLOW_UP_DELIMITER) + 4

                for piece in self.llm_provider.stream_generate(
                    messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                ):
                    raw_chunks.append(piece)
                    if delimiter_seen:
                        continue
                    pending += piece
                    idx = pending.find(FOLLOW_UP_DELIMITER)
                    if idx != -1:
                        to_emit = pending[:idx].rstrip()
                        if to_emit:
                            yield {"event": "delta", "data": {"text": to_emit}}
                        pending = ""
                        delimiter_seen = True
                    elif len(pending) > guard_len:
                        emit_len = len(pending) - guard_len
                        yield {"event": "delta", "data": {"text": pending[:emit_len]}}
                        pending = pending[emit_len:]

                if not delimiter_seen and pending:
                    cleaned_tail = pending.rstrip()
                    if cleaned_tail:
                        yield {"event": "delta", "data": {"text": cleaned_tail}}

                full_raw = "".join(raw_chunks).strip()
                answer, follow_ups = _parse_answer_and_followups(full_raw)
                if answer:
                    updated_citations = _mark_used_citations(answer, prepared.citations)
                    response = QueryResponse(
                        answer=answer,
                        citations=updated_citations,
                        latency_ms=self._elapsed_ms(started),
                        generation_mode="llm",
                        model_used=self.llm_provider.model_name,
                        provider_used=self.llm_provider.provider_name,
                        rewritten_query=prepared.rewritten_query,
                        follow_up_questions=follow_ups or self._heuristic_followups(prepared.citations),
                        conversation_id=req.conversation_id,
                    )
                    self._persist_turn(req, response)
                    yield {"event": "done", "data": response.model_dump(mode="json", by_alias=True)}
                    return
                warning_msg = f"Model {self.llm_provider.model_name} trả về nội dung rỗng; đã chuyển sang trích xuất dự phòng."
            except Exception as exc:
                logger.warning("LLM streaming failed; using extractive fallback: %s", exc)
                warning_msg = f"Không thể gọi AI model ({self.llm_provider.model_name}): {exc}"
        else:
            warning_msg = self._missing_llm_warning()

        fallback_answer = self._build_extractive_fallback(prepared.citations)
        yield {"event": "delta", "data": {"text": fallback_answer}}
        response = QueryResponse(
            answer=fallback_answer,
            citations=prepared.citations,
            latency_ms=self._elapsed_ms(started),
            generation_mode="extractive_fallback",
            model_used=self.llm_provider.model_name or None,
            provider_used=self.llm_provider.provider_name,
            rewritten_query=prepared.rewritten_query,
            follow_up_questions=self._heuristic_followups(prepared.citations),
            warning=warning_msg,
            conversation_id=req.conversation_id,
        )
        self._persist_turn(req, response)
        yield {"event": "done", "data": response.model_dump(mode="json", by_alias=True)}

    def _prepare_retrieval(self, req: QueryRequest) -> _PreparedRetrieval:
        question = req.question.strip()
        if not question:
            raise ValueError("Câu hỏi không được để trống.")

        tenant = (req.tenant_id or self.settings.default_tenant_id).strip()
        if not tenant:
            raise ValueError("tenant_id không hợp lệ.")

        history = list(req.history)
        if not history and req.conversation_id and self.workspace_store is not None:
            conv = self.workspace_store.get_conversation(req.conversation_id)
            if conv and conv.messages:
                history = [
                    ChatTurn(role=m.role, content=m.content)
                    for m in conv.messages[-6:]
                    if m.content.strip()
                ]

        effective_doc_ids = req.document_ids
        if effective_doc_ids is None and req.notebook_id and self.workspace_store is not None:
            nb = self.workspace_store.get_notebook(req.notebook_id)
            if nb is not None:
                effective_doc_ids = list(nb.document_ids)

        if effective_doc_ids is not None and len(effective_doc_ids) == 0:
            return _PreparedRetrieval(
                question=question,
                search_query=question,
                rewritten_query=None,
                history=history,
                citations=[],
                context_blocks=[],
                early_answer=EMPTY_SCOPE_ANSWER,
            )

        scope = self._resolve_scope(req=req, tenant=tenant, effective_doc_ids=effective_doc_ids)
        if scope is None:
            return _PreparedRetrieval(
                question=question,
                search_query=question,
                rewritten_query=None,
                history=history,
                citations=[],
                context_blocks=[],
                early_answer=EMPTY_SCOPE_ANSWER,
            )

        rewritten = self.query_rewriter.rewrite(question, history)
        search_query = rewritten if rewritten else question
        rewritten_flag = rewritten if rewritten != question else None

        search_filter, departments, access_groups, doc_ids = scope
        candidate_k = max(req.top_k * 3, self.settings.retrieval_candidate_k)

        query_vectors = self.embedder.embed_texts([search_query], task_type="RETRIEVAL_QUERY")
        dense_hits = (
            self.vector_store.vector_search(
                query_vectors[0],
                search_filter=search_filter,
                top_k=candidate_k,
            )
            if query_vectors
            else []
        )

        bm25_hits = self.bm25_index.search(
            search_query,
            tenant_id=tenant,
            departments=departments,
            access_groups=access_groups,
            document_ids=doc_ids,
            only_enabled=True,
            top_k=candidate_k,
        )

        keyword_hits = []
        try:
            keyword_hits = self.vector_store.keyword_search(
                search_query,
                search_filter=search_filter,
                top_k=candidate_k,
            )
        except Exception as exc:
            logger.debug("Keyword search skipped due to store error: %s", exc)

        chunk_map: dict[str, ChunkRecord] = {}
        dense_scores: dict[str, float] = {}
        for hit in dense_hits:
            chunk_map[hit.chunk.id] = hit.chunk
            dense_scores[hit.chunk.id] = float(hit.score)
        for hit in keyword_hits:
            chunk_map.setdefault(hit.chunk.id, hit.chunk)

        sparse_ranks: list[tuple[str, float]] = bm25_hits or [
            (hit.chunk.id, float(hit.score)) for hit in keyword_hits
        ]
        self._resolve_missing_chunks(
            chunk_ids=[cid for cid, _ in sparse_ranks],
            chunk_map=chunk_map,
            allowed_doc_ids=doc_ids,
        )

        rrf_scores = self._fuse_rrf(
            dense_ids=[hit.chunk.id for hit in dense_hits],
            sparse_ids=[cid for cid, _ in sparse_ranks if cid in chunk_map],
        )

        pool = [
            RerankCandidate(
                chunk=chunk_map[cid],
                rrf_score=score,
                dense_score=dense_scores.get(cid),
            )
            for cid, score in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
            if cid in chunk_map
        ]

        if not pool:
            return _PreparedRetrieval(
                question=question,
                search_query=search_query,
                rewritten_query=rewritten_flag,
                history=history,
                citations=[],
                context_blocks=[],
                early_answer=NO_MATCH_ANSWER,
            )

        if req.use_reranker is False:
            ranked_candidates = pool[: req.top_k]
            max_rrf = max(c.rrf_score for c in ranked_candidates) or 1.0
            for c in ranked_candidates:
                c.rerank_score = c.rrf_score / max_rrf
        else:
            ranked_candidates = self.reranker.rerank(search_query, pool, top_k=req.top_k)

        max_rrf = max(c.rrf_score for c in ranked_candidates) or 1.0
        citations: list[CitationItem] = []
        context_blocks: list[str] = []
        used_tokens = 0

        for idx, cand in enumerate(ranked_candidates, start=1):
            chunk = cand.chunk
            display_score = self._compute_display_score(
                dense_score=cand.dense_score,
                rrf_score=cand.rrf_score,
                max_rrf=max_rrf,
                rerank_score=cand.rerank_score,
            )
            expanded_text = self._expand_parent_context(chunk)
            parent_content = expanded_text if expanded_text.strip() != chunk.content.strip() else None
            highlight = _extract_query_highlight(chunk.content, search_query, fallback=chunk.highlight)

            citations.append(
                CitationItem(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=chunk.document_title,
                    category=chunk.category,
                    section=chunk.section,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    highlight=highlight,
                    citation_number=idx,
                    score=display_score,
                    used_in_answer=True,
                    parent_content=parent_content,
                )
            )

            page_info = f" | Trang {chunk.page}" if chunk.page is not None else ""
            block = f"[{idx}] Tài liệu: {chunk.document_title} | Mục: {chunk.section}{page_info}\n{expanded_text}"
            block_tokens = count_tokens(block)
            if context_blocks and used_tokens + block_tokens > self.settings.context_max_tokens:
                continue
            context_blocks.append(block)
            used_tokens += block_tokens

        return _PreparedRetrieval(
            question=question,
            search_query=search_query,
            rewritten_query=rewritten_flag,
            history=history,
            citations=citations,
            context_blocks=context_blocks,
        )

    def _resolve_scope(
        self,
        *,
        req: QueryRequest,
        tenant: str,
        effective_doc_ids: list[str] | None,
    ) -> tuple[SearchFilter, list[str], list[str], list[str]] | None:
        explicit_depts = [d.strip() for d in (req.departments or []) if d.strip()]
        explicit_groups = [g.strip() for g in (req.access_groups or []) if g.strip()]
        requested_docs = [d.strip() for d in (effective_doc_ids or []) if d.strip()]

        if explicit_depts or explicit_groups:
            search_filter = SearchFilter(
                tenant_id=tenant,
                departments=explicit_depts,
                access_groups=explicit_groups,
                document_ids=requested_docs,
                only_enabled=True,
                allow_unscoped_admin=False,
            )
            return search_filter, explicit_depts, explicit_groups, requested_docs

        tenant_docs = self.vector_store.list_documents(tenant_id=tenant)
        ready_docs = [d for d in tenant_docs if d.enabled and d.status == "ready"]
        if effective_doc_ids is not None:
            allowed_set = set(requested_docs)
            ready_docs = [d for d in ready_docs if d.id in allowed_set]

        if not ready_docs:
            return None

        departments = sorted({d.department for d in ready_docs if d.department and d.department.strip()})
        doc_ids = [d.id for d in ready_docs]
        if not departments:
            return None

        search_filter = SearchFilter(
            tenant_id=tenant,
            departments=departments,
            access_groups=[],
            document_ids=doc_ids,
            only_enabled=True,
            allow_unscoped_admin=False,
        )
        return search_filter, departments, [], doc_ids

    def _resolve_missing_chunks(
        self,
        *,
        chunk_ids: list[str],
        chunk_map: dict[str, ChunkRecord],
        allowed_doc_ids: list[str],
    ) -> None:
        missing = {cid for cid in chunk_ids if cid not in chunk_map}
        if not missing:
            return

        doc_ids_to_fetch: set[str] = set()
        for entry in getattr(self.bm25_index, "_flat_entries", []):
            if entry.get("chunk_id") in missing and entry.get("document_id"):
                doc_ids_to_fetch.add(entry["document_id"])
        if not doc_ids_to_fetch:
            doc_ids_to_fetch.update(allowed_doc_ids)

        for doc_id in doc_ids_to_fetch:
            for chunk in self.vector_store.get_document_chunks(doc_id):
                if chunk.enabled:
                    chunk_map.setdefault(chunk.id, chunk)

    @staticmethod
    def _fuse_rrf(*, dense_ids: list[str], sparse_ids: list[str], rrf_k: int = 60) -> dict[str, float]:
        scores: dict[str, float] = {}
        for rank, cid in enumerate(dense_ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        for rank, cid in enumerate(sparse_ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        return scores

    @staticmethod
    def _compute_display_score(
        *,
        dense_score: float | None,
        rrf_score: float,
        max_rrf: float,
        rerank_score: float = 0.0,
    ) -> float:
        if dense_score is not None and rerank_score > 0:
            blended = 0.55 * max(0.0, min(1.0, dense_score)) + 0.45 * max(0.0, min(1.0, rerank_score))
            return round(max(0.0, min(1.0, blended)), 2)
        if dense_score is not None:
            clamped = max(0.0, min(1.0, dense_score))
            return round(clamped, 2)
        if rerank_score > 0:
            return round(max(0.35, min(0.95, rerank_score)), 2)
        normalized = max(0.35, min(0.95, (rrf_score / max_rrf) * 0.85))
        return round(normalized, 2)

    def _expand_parent_context(self, chunk: ChunkRecord) -> str:
        if chunk.parent_id:
            parent = self.vector_store.get_parent_chunk(chunk.parent_id)
            if parent and parent.content.strip():
                return parent.content
        return chunk.content

    @staticmethod
    def _build_llm_messages(
        *,
        question: str,
        history: list[ChatTurn],
        context_blocks: list[str],
    ) -> list[LLMMessage]:
        messages: list[LLMMessage] = [LLMMessage(role="system", content=SYSTEM_PROMPT)]
        for turn in history[-6:]:
            if turn.content.strip():
                messages.append(LLMMessage(role=turn.role, content=turn.content.strip()[:1200]))

        context_text = "\n\n---\n\n".join(context_blocks)
        user_prompt = f"Ngữ cảnh tài liệu:\n{context_text}\n\nCâu hỏi: {question}"
        messages.append(LLMMessage(role="user", content=user_prompt))
        return messages

    def _missing_llm_warning(self) -> str:
        if self.llm_provider.provider_name == "none":
            return "LLM đang tắt (LLM_PROVIDER=none). Đang hiển thị đoạn trích trực tiếp từ tài liệu."
        return (
            f"Chưa cấu hình API key cho {self.llm_provider.provider_name}. "
            "Đang hiển thị đoạn trích trực tiếp từ tài liệu."
        )

    def _generate_answer(
        self,
        *,
        question: str,
        history: list[ChatTurn],
        context_blocks: list[str],
        citations: list[CitationItem],
    ) -> tuple[str, str, str | None, str | None, list[str], str | None]:
        if self.llm_provider.is_configured:
            messages = self._build_llm_messages(
                question=question,
                history=history,
                context_blocks=context_blocks,
            )
            try:
                result = self.llm_provider.generate(
                    messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                answer, follow_ups = _parse_answer_and_followups(result.text)
                if answer:
                    return (
                        answer,
                        "llm",
                        result.model,
                        result.provider,
                        follow_ups or self._heuristic_followups(citations),
                        None,
                    )
                warning = f"Model {self.llm_provider.model_name} trả về nội dung rỗng; đã chuyển sang trích xuất dự phòng."
            except Exception as exc:
                logger.warning("LLM answer generation failed; using extractive fallback: %s", exc)
                warning = f"Không thể gọi AI model ({self.llm_provider.model_name}): {exc}"
        else:
            warning = self._missing_llm_warning()

        return (
            self._build_extractive_fallback(citations),
            "extractive_fallback",
            self.llm_provider.model_name or None,
            self.llm_provider.provider_name,
            self._heuristic_followups(citations),
            warning,
        )

    @staticmethod
    def _heuristic_followups(citations: list[CitationItem]) -> list[str]:
        questions: list[str] = []
        seen_titles: set[str] = set()
        for cit in citations:
            if cit.document_title in seen_titles:
                continue
            seen_titles.add(cit.document_title)
            questions.append(f"Tóm tắt các điểm chính trong mục \"{cit.section}\" của {cit.document_title}?")
            if len(questions) >= 2:
                break
        if citations:
            questions.append(f"Có ngoại lệ hoặc lưu ý đặc biệt nào liên quan đến {citations[0].document_title} không?")
        return questions[:3]

    @staticmethod
    def _build_extractive_fallback(citations: list[CitationItem]) -> str:
        paragraphs: list[str] = []
        for cit in citations[:3]:
            snippet = " ".join(cit.content.split())
            if len(snippet) > 420:
                snippet = snippet[:417].rsplit(" ", 1)[0] + "..."
            paragraphs.append(
                f"Theo tài liệu **{cit.document_title}** ({cit.section}): {snippet} [{cit.citation_number}]"
            )
        return (
            "\n\n".join(paragraphs)
            + "\n\nBạn có thể nhấn trực tiếp vào từng số trích dẫn để đối chiếu nguyên văn đoạn tài liệu ở khung bên phải."
        )

    def _persist_turn(self, req: QueryRequest, response: QueryResponse) -> None:
        if not req.conversation_id or self.workspace_store is None:
            return
        now = utc_now_iso()
        user_msg = ConversationMessage(
            id=f"msg-u-{uuid.uuid4().hex[:8]}",
            role="user",
            content=req.question.strip(),
            created_at=now,
        )
        asst_msg = ConversationMessage(
            id=f"msg-a-{uuid.uuid4().hex[:8]}",
            role="assistant",
            content=response.answer,
            created_at=now,
            citations=response.citations,
            latency_ms=response.latency_ms,
            generation_mode=response.generation_mode,
            model_used=response.model_used,
            provider_used=response.provider_used,
            follow_up_questions=response.follow_up_questions,
            warning=response.warning,
        )
        self.workspace_store.append_messages(
            req.conversation_id,
            [user_msg, asst_msg],
            auto_title=req.question.strip(),
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(1, int((time.perf_counter() - started) * 1000))
