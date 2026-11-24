from __future__ import annotations

from abc import ABC, abstractmethod

from src.schemas.chunk import ChunkRecord, DLQRecord, IngestionJobResult, ParentChunk, SearchFilter, SearchResult
from src.schemas.document import DocumentItem


def is_filter_authorized(flt: SearchFilter) -> bool:
    """Enforce fail-closed isolation: require tenant_id and >=1 department or access_group."""
    if flt.allow_unscoped_admin:
        return True
    if not flt.tenant_id or not flt.tenant_id.strip():
        return False
    has_dept = any(d.strip() for d in flt.departments)
    has_group = any(g.strip() for g in flt.access_groups)
    return has_dept or has_group


class VectorStore(ABC):
    """Abstract storage & vector search contract (MongoDB Dual-Mode / InMemory)."""

    @abstractmethod
    def ensure_indexes(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def ping(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def upsert_document(self, doc: DocumentItem) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_document(self, document_id: str) -> DocumentItem | None:
        raise NotImplementedError

    @abstractmethod
    def list_documents(self, *, tenant_id: str | None = None, department: str | None = None) -> list[DocumentItem]:
        raise NotImplementedError

    @abstractmethod
    def set_document_enabled(self, document_id: str, enabled: bool) -> DocumentItem | None:
        raise NotImplementedError

    @abstractmethod
    def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[ChunkRecord],
        parent_chunks: list[ParentChunk] | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_document_chunks(self, document_id: str) -> list[ChunkRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_parent_chunk(self, parent_id: str) -> ParentChunk | None:
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, document_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def vector_search(
        self,
        query_vector: list[float],
        *,
        search_filter: SearchFilter,
        top_k: int = 5,
        num_candidates: int = 100,
    ) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    def keyword_search(
        self,
        query_text: str,
        *,
        search_filter: SearchFilter,
        top_k: int = 5,
    ) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    def record_job(self, job: IngestionJobResult) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_jobs(self, limit: int = 20) -> list[IngestionJobResult]:
        raise NotImplementedError

    @abstractmethod
    def record_dlq(self, record: DLQRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_dlq(self, limit: int = 50) -> list[DLQRecord]:
        raise NotImplementedError

    @abstractmethod
    def stats(self) -> dict:
        raise NotImplementedError
