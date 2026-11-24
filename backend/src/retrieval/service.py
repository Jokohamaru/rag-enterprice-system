from __future__ import annotations

import logging
import time

from src.config.settings import Settings
from src.ingestion.embedders.base import EmbeddingProvider
from src.ingestion.sparse_indexer import SparseBM25Index
from src.schemas.chunk import ChunkRecord, SearchFilter
from src.schemas.query import CitationItem, QueryRequest, QueryResponse
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


class RAGQueryService:
    """Hybrid Search (Vector + BM25 via RRF), Small-to-Big context expansion, and grounded generation."""

    def __init__(
        self,
        *,
        settings: Settings,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        bm25_index: SparseBM25Index,
    ) -> None:
        self.settings = settings
        self.vector_store = vector_store
        self.embedder = embedder
        self.bm25_index = bm25_index
        self._genai_client = None

    def query(self, req: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        question = req.question.strip()
        if not question:
            raise ValueError("Câu hỏi không được để trống.")

        tenant = (req.tenant_id or self.settings.default_tenant_id).strip()
        if not tenant:
            raise ValueError("tenant_id không hợp lệ.")

        if req.document_ids is not None and len(req.document_ids) == 0:
            return QueryResponse(
                answer=EMPTY_SCOPE_ANSWER,
                citations=[],
                latency_ms=self._elapsed_ms(started),
            )

        scope = self._resolve_scope(req=req, tenant=tenant)
        if scope is None:
            return QueryResponse(
                answer=EMPTY_SCOPE_ANSWER,
                citations=[],
                latency_ms=self._elapsed_ms(started),
            )

        search_filter, departments, access_groups, doc_ids = scope
        candidate_k = max(req.top_k * 3, 10)

        query_vectors = self.embedder.embed_texts([question], task_type="RETRIEVAL_QUERY")
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
            question,
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
                question,
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
        ranked_ids = [
            cid
            for cid, _ in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
            if cid in chunk_map
        ][: req.top_k]

        if not ranked_ids:
            return QueryResponse(
                answer=NO_MATCH_ANSWER,
                citations=[],
                latency_ms=self._elapsed_ms(started),
            )

        max_rrf = max(rrf_scores[cid] for cid in ranked_ids) or 1.0
        citations: list[CitationItem] = []
        context_blocks: list[str] = []

        for idx, cid in enumerate(ranked_ids, start=1):
            chunk = chunk_map[cid]
            display_score = self._compute_display_score(
                dense_score=dense_scores.get(cid),
                rrf_score=rrf_scores[cid],
                max_rrf=max_rrf,
            )
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
                    highlight=chunk.highlight,
                    citation_number=idx,
                    score=display_score,
                )
            )
            expanded_text = self._expand_parent_context(chunk)
            page_info = f" | Trang {chunk.page}" if chunk.page is not None else ""
            context_blocks.append(
                f"[{idx}] Tài liệu: {chunk.document_title} | Mục: {chunk.section}{page_info}\n{expanded_text}"
            )

        answer = self._generate_answer(question=question, context_blocks=context_blocks, citations=citations)
        return QueryResponse(
            answer=answer,
            citations=citations,
            latency_ms=self._elapsed_ms(started),
        )

    def _resolve_scope(
        self,
        *,
        req: QueryRequest,
        tenant: str,
    ) -> tuple[SearchFilter, list[str], list[str], list[str]] | None:
        explicit_depts = [d.strip() for d in (req.departments or []) if d.strip()]
        explicit_groups = [g.strip() for g in (req.access_groups or []) if g.strip()]
        requested_docs = [d.strip() for d in (req.document_ids or []) if d.strip()]

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
        if req.document_ids is not None:
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
    def _compute_display_score(*, dense_score: float | None, rrf_score: float, max_rrf: float) -> float:
        if dense_score is not None:
            clamped = max(0.0, min(1.0, dense_score))
            return round(clamped, 2)
        normalized = max(0.35, min(0.95, (rrf_score / max_rrf) * 0.85))
        return round(normalized, 2)

    def _expand_parent_context(self, chunk: ChunkRecord) -> str:
        if chunk.parent_id:
            parent = self.vector_store.get_parent_chunk(chunk.parent_id)
            if parent and parent.content.strip():
                return parent.content
        return chunk.content

    def _generate_answer(
        self,
        *,
        question: str,
        context_blocks: list[str],
        citations: list[CitationItem],
    ) -> str:
        api_key = self.settings.gemini_api_key.strip()
        if api_key and self.settings.embedding_provider != "mock":
            try:
                if self._genai_client is None:
                    from google import genai

                    self._genai_client = genai.Client(api_key=api_key)

                context_text = "\n\n---\n\n".join(context_blocks)
                prompt = (
                    "Bạn là trợ lý tra cứu tài liệu nội bộ doanh nghiệp. Hãy trả lời câu hỏi của người dùng "
                    "CHỈ dựa trên các đoạn tài liệu được cung cấp bên dưới.\n"
                    "Quy tắc bắt buộc:\n"
                    "1. Trả lời bằng tiếng Việt rõ ràng, súc tích, chính xác và không suy diễn ngoài ngữ cảnh.\n"
                    "2. Gắn số trích dẫn dạng [1], [2]... ngay sau các thông tin lấy từ đoạn tương ứng.\n"
                    "3. Có thể dùng **in đậm** cho ý chính và tách các đoạn bằng một dòng trống.\n"
                    "4. Nếu các đoạn tài liệu không đủ thông tin để trả lời, hãy nêu rõ thông tin còn thiếu.\n\n"
                    f"Ngữ cảnh tài liệu:\n{context_text}\n\n"
                    f"Câu hỏi: {question}"
                )
                response = self._genai_client.models.generate_content(
                    model=self.settings.gemini_generation_model,
                    contents=prompt,
                )
                generated = (response.text or "").strip()
                if generated:
                    return generated
            except Exception as exc:
                logger.warning("Gemini answer generation failed; using extractive fallback: %s", exc)

        return self._build_extractive_fallback(citations)

    @staticmethod
    def _build_extractive_fallback(citations: list[CitationItem]) -> str:
        paragraphs: list[str] = []
        for cit in citations[:2]:
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

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(1, int((time.perf_counter() - started) * 1000))
