from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    """Query payload aligned with `frontend/src/types/rag.ts`."""

    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(min_length=1)
    document_ids: list[str] | None = Field(default=None, alias="documentIds")
    top_k: int = Field(default=3, ge=1, le=20, alias="topK")
    tenant_id: str | None = Field(default=None, alias="tenantId")
    departments: list[str] | None = None
    access_groups: list[str] | None = Field(default=None, alias="accessGroups")


class CitationItem(BaseModel):
    """Retrieved chunk citation serialized in camelCase for the frontend."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    document_id: str = Field(alias="documentId", serialization_alias="documentId")
    document_title: str = Field(alias="documentTitle", serialization_alias="documentTitle")
    category: str
    section: str
    page: int | None = None
    chunk_index: int = Field(alias="chunkIndex", serialization_alias="chunkIndex")
    content: str
    highlight: str | None = None
    citation_number: int = Field(alias="citationNumber", serialization_alias="citationNumber")
    score: float


class QueryResponse(BaseModel):
    """RAG answer and grounded citations returned by `POST /api/v1/query`."""

    model_config = ConfigDict(populate_by_name=True)

    answer: str
    citations: list[CitationItem]
    latency_ms: int = Field(alias="latencyMs", serialization_alias="latencyMs")
