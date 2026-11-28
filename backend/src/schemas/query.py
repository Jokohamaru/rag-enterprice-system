from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatTurn(BaseModel):
    """Single historical turn sent for multi-turn query rewriting and memory."""

    model_config = ConfigDict(populate_by_name=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class QueryRequest(BaseModel):
    """Query payload aligned with `frontend/src/types/rag.ts`."""

    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(min_length=1)
    document_ids: list[str] | None = Field(default=None, alias="documentIds")
    top_k: int = Field(default=6, ge=1, le=20, alias="topK")
    tenant_id: str | None = Field(default=None, alias="tenantId")
    departments: list[str] | None = None
    access_groups: list[str] | None = Field(default=None, alias="accessGroups")
    history: list[ChatTurn] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None, alias="conversationId")
    notebook_id: str | None = Field(default=None, alias="notebookId")
    use_reranker: bool | None = Field(default=None, alias="useReranker")


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
    used_in_answer: bool = Field(default=True, alias="usedInAnswer", serialization_alias="usedInAnswer")
    parent_content: str | None = Field(default=None, alias="parentContent", serialization_alias="parentContent")


class QueryResponse(BaseModel):
    """RAG answer and grounded citations returned by `POST /api/v1/query`."""

    model_config = ConfigDict(populate_by_name=True)

    answer: str
    citations: list[CitationItem]
    latency_ms: int = Field(alias="latencyMs", serialization_alias="latencyMs")
    generation_mode: Literal["llm", "extractive_fallback"] = Field(
        default="extractive_fallback",
        alias="generationMode",
        serialization_alias="generationMode",
    )
    model_used: str | None = Field(default=None, alias="modelUsed", serialization_alias="modelUsed")
    provider_used: str | None = Field(default=None, alias="providerUsed", serialization_alias="providerUsed")
    rewritten_query: str | None = Field(
        default=None,
        alias="rewrittenQuery",
        serialization_alias="rewrittenQuery",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        alias="followUpQuestions",
        serialization_alias="followUpQuestions",
    )
    warning: str | None = None
    conversation_id: str | None = Field(
        default=None,
        alias="conversationId",
        serialization_alias="conversationId",
    )
