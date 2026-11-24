from __future__ import annotations

import re

import numpy as np

from src.ingestion.sparse_indexer import tokenize_for_bm25
from src.schemas.chunk import ChunkRecord, DLQRecord, IngestionJobResult, ParentChunk, SearchFilter, SearchResult
from src.schemas.document import DocumentItem
from src.vectordb.base import VectorStore, is_filter_authorized


class InMemoryVectorStore(VectorStore):
    """In-memory VectorStore mirroring MongoDB Dual-Mode behavior for fast isolated tests."""

    def __init__(self) -> None:
        self.documents: dict[str, DocumentItem] = {}
        self.chunks: dict[str, ChunkRecord] = {}
        self.parents: dict[str, ParentChunk] = {}
        self.jobs: list[IngestionJobResult] = []
        self.dlq: list[DLQRecord] = []

    def ensure_indexes(self) -> None:
        return None

    def ping(self) -> dict:
        return {"ok": True, "backend": "memory", "vector_mode": "memory"}

    def upsert_document(self, doc: DocumentItem) -> None:
        self.documents[doc.id] = doc

    def get_document(self, document_id: str) -> DocumentItem | None:
        return self.documents.get(document_id)

    def list_documents(self, *, tenant_id: str | None = None, department: str | None = None) -> list[DocumentItem]:
        docs = list(self.documents.values())
        if tenant_id:
            docs = [d for d in docs if d.tenant_id == tenant_id]
        if department:
            docs = [d for d in docs if d.department == department]
        docs.sort(key=lambda d: d.updated_at, reverse=True)
        return docs

    def set_document_enabled(self, document_id: str, enabled: bool) -> DocumentItem | None:
        doc = self.documents.get(document_id)
        if doc is None:
            return None
        updated = doc.model_copy(update={"enabled": enabled})
        self.documents[document_id] = updated
        for cid, ch in list(self.chunks.items()):
            if ch.document_id == document_id:
                self.chunks[cid] = ch.model_copy(update={"enabled": enabled})
        return updated

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[ChunkRecord],
        parent_chunks: list[ParentChunk] | None = None,
    ) -> None:
        for cid in [k for k, v in self.chunks.items() if v.document_id == document_id]:
            del self.chunks[cid]
        for pid in [k for k, v in self.parents.items() if v.document_id == document_id]:
            del self.parents[pid]
        for c in chunks:
            self.chunks[c.id] = c
        for p in parent_chunks or []:
            self.parents[p.parent_id] = p

    def get_document_chunks(self, document_id: str) -> list[ChunkRecord]:
        items = [c for c in self.chunks.values() if c.document_id == document_id]
        items.sort(key=lambda c: c.chunk_index)
        return items

    def get_parent_chunk(self, parent_id: str) -> ParentChunk | None:
        return self.parents.get(parent_id)

    def delete_document(self, document_id: str) -> bool:
        existed = document_id in self.documents
        self.documents.pop(document_id, None)
        for cid in [k for k, v in self.chunks.items() if v.document_id == document_id]:
            del self.chunks[cid]
            existed = True
        for pid in [k for k, v in self.parents.items() if v.document_id == document_id]:
            del self.parents[pid]
        return existed

    def _filter_chunks(self, flt: SearchFilter) -> list[ChunkRecord]:
        if not is_filter_authorized(flt):
            return []
        dept_set = {d.strip() for d in flt.departments if d.strip()}
        grp_set = {g.strip() for g in flt.access_groups if g.strip()}
        doc_set = {d.strip() for d in flt.document_ids if d.strip()}

        out: list[ChunkRecord] = []
        for c in self.chunks.values():
            if not flt.allow_unscoped_admin:
                if c.tenant_id != flt.tenant_id:
                    continue
                dept_ok = bool(dept_set and c.department in dept_set)
                grp_ok = bool(grp_set and grp_set.intersection(c.access_groups))
                if not (dept_ok or grp_ok):
                    continue
            if flt.only_enabled and not c.enabled:
                continue
            if doc_set and c.document_id not in doc_set:
                continue
            out.append(c)
        return out

    def vector_search(
        self,
        query_vector: list[float],
        *,
        search_filter: SearchFilter,
        top_k: int = 5,
        num_candidates: int = 100,
    ) -> list[SearchResult]:
        candidates = self._filter_chunks(search_filter)
        if not candidates or not query_vector:
            return []

        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = float(np.linalg.norm(q))
        if q_norm > 1e-12:
            q = q / q_norm

        mat = np.asarray([c.embedding for c in candidates], dtype=np.float32)
        scores = mat @ q
        ranked_idx = np.argsort(-scores)[:top_k]
        return [
            SearchResult(chunk=candidates[int(i)], score=float(scores[int(i)]), source="vector")
            for i in ranked_idx
        ]

    def keyword_search(
        self,
        query_text: str,
        *,
        search_filter: SearchFilter,
        top_k: int = 5,
    ) -> list[SearchResult]:
        candidates = self._filter_chunks(search_filter)
        q_tokens = set(tokenize_for_bm25(query_text))
        if not candidates or not q_tokens:
            return []

        scored: list[SearchResult] = []
        for c in candidates:
            hay = set(tokenize_for_bm25(f"{c.document_title} {c.section} {c.content}"))
            overlap = len(q_tokens.intersection(hay))
            if overlap > 0:
                score = overlap / len(q_tokens)
                scored.append(SearchResult(chunk=c, score=float(score), source="keyword"))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def record_job(self, job: IngestionJobResult) -> None:
        self.jobs.insert(0, job)

    def list_jobs(self, limit: int = 20) -> list[IngestionJobResult]:
        return self.jobs[:limit]

    def record_dlq(self, record: DLQRecord) -> None:
        self.dlq.insert(0, record)

    def list_dlq(self, limit: int = 50) -> list[DLQRecord]:
        return self.dlq[:limit]

    def stats(self) -> dict:
        by_dept: dict[str, int] = {}
        for c in self.chunks.values():
            by_dept[c.department] = by_dept.get(c.department, 0) + 1
        return {
            "backend": "memory",
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "parent_chunks": len(self.parents),
            "dlq_events": len(self.dlq),
            "chunks_by_department": by_dept,
        }
