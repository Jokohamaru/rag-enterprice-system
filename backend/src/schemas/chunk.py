from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.document import DocumentFormat, utc_now_iso


class ExtractedPage(BaseModel):
    """Single cleaned page or logical section extracted from a source document."""

    page_number: int = Field(ge=1)
    section: str = "Tổng quan"
    text: str


class ExtractedDocument(BaseModel):
    """Structured document output produced by loaders and cleaner."""

    title: str
    format: DocumentFormat
    pages: list[ExtractedPage]
    summary: str = ""


class ParentChunk(BaseModel):
    """Coarse parent chunk stored for Small-to-Big retrieval."""

    model_config = ConfigDict(populate_by_name=True)

    parent_id: str
    document_id: str
    tenant_id: str
    department: str
    section: str
    page: int | None = None
    chunk_index: int
    content: str
    token_count: int


class ChunkRecord(BaseModel):
    """Indexed vector chunk matching frontend `DocumentChunk` + isolation metadata."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    document_id: str = Field(alias="documentId", serialization_alias="documentId")
    document_title: str = Field(alias="documentTitle", serialization_alias="documentTitle")
    category: str
    section: str
    page: int | None = None
    chunk_index: int = Field(alias="chunkIndex", serialization_alias="chunkIndex")
    content: str
    contextual_content: str = ""
    highlight: str | None = None
    parent_id: str | None = None
    token_count: int = 0

    # Isolation & deduplication metadata
    tenant_id: str
    department: str
    access_groups: list[str] = Field(default_factory=list)
    enabled: bool = True
    content_hash: str = ""
    embedding: list[float] = Field(default_factory=list)


class SearchFilter(BaseModel):
    """Mandatory pre-filter enforced at Vector DB retrieval time (fail-closed)."""

    tenant_id: str = ""
    departments: list[str] = Field(default_factory=list)
    access_groups: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    only_enabled: bool = True
    allow_unscoped_admin: bool = False


class SearchResult(BaseModel):
    """Vector or keyword search hit returned by the VectorStore."""

    chunk: ChunkRecord
    score: float
    source: Literal["vector", "keyword", "hybrid"] = "vector"


class IngestionJobResult(BaseModel):
    """Audit log of an ingestion or batch sync run."""

    job_id: str
    trigger: Literal["upload", "sync", "cli"] = "upload"
    status: Literal["completed", "partial", "failed"] = "completed"
    processed_files: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    document_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: str = Field(default_factory=utc_now_iso)
    finished_at: str = Field(default_factory=utc_now_iso)


class DLQRecord(BaseModel):
    """Dead-letter event captured when sidecar validation or ingestion fails."""

    dlq_id: str
    file_path: str
    document_id: str | None = None
    tenant_id: str | None = None
    department: str | None = None
    stage: Literal["staging", "sidecar_safeguard", "loading", "chunking", "embedding", "indexing"]
    error: str
    created_at: str = Field(default_factory=utc_now_iso)
