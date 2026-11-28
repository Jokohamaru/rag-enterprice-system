from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.document import utc_now_iso
from src.schemas.query import CitationItem

NoteType = Literal["pinned", "summary", "faq", "briefing", "study_guide", "comparison_table", "custom"]
StudioGenerateType = Literal["summary", "faq", "briefing", "study_guide", "comparison_table"]


class NotebookItem(BaseModel):
    """Notebook grouping selected sources, overview, and suggested starter questions."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    description: str = ""
    document_ids: list[str] = Field(default_factory=list, alias="documentIds", serialization_alias="documentIds")
    overview: str = ""
    suggested_questions: list[str] = Field(
        default_factory=list,
        alias="suggestedQuestions",
        serialization_alias="suggestedQuestions",
    )
    created_at: str = Field(default_factory=utc_now_iso, alias="createdAt", serialization_alias="createdAt")
    updated_at: str = Field(default_factory=utc_now_iso, alias="updatedAt", serialization_alias="updatedAt")


class NotebookCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")


class NotebookUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    document_ids: list[str] | None = Field(default=None, alias="documentIds")
    overview: str | None = None
    suggested_questions: list[str] | None = Field(default=None, alias="suggestedQuestions")


class NotebookOverviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    notebook_id: str | None = Field(default=None, alias="notebookId")
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")


class NotebookOverviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    overview: str
    suggested_questions: list[str] = Field(
        default_factory=list,
        alias="suggestedQuestions",
        serialization_alias="suggestedQuestions",
    )
    model_used: str | None = Field(default=None, alias="modelUsed", serialization_alias="modelUsed")
    generation_mode: Literal["llm", "extractive_fallback"] = Field(
        default="extractive_fallback",
        alias="generationMode",
        serialization_alias="generationMode",
    )


class ConversationMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str = Field(default_factory=utc_now_iso, alias="createdAt", serialization_alias="createdAt")
    citations: list[CitationItem] = Field(default_factory=list)
    latency_ms: int | None = Field(default=None, alias="latencyMs", serialization_alias="latencyMs")
    generation_mode: Literal["llm", "extractive_fallback"] | None = Field(
        default=None,
        alias="generationMode",
        serialization_alias="generationMode",
    )
    model_used: str | None = Field(default=None, alias="modelUsed", serialization_alias="modelUsed")
    provider_used: str | None = Field(default=None, alias="providerUsed", serialization_alias="providerUsed")
    follow_up_questions: list[str] = Field(
        default_factory=list,
        alias="followUpQuestions",
        serialization_alias="followUpQuestions",
    )
    warning: str | None = None


class ConversationItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    notebook_id: str | None = Field(default=None, alias="notebookId", serialization_alias="notebookId")
    messages: list[ConversationMessage] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso, alias="createdAt", serialization_alias="createdAt")
    updated_at: str = Field(default_factory=utc_now_iso, alias="updatedAt", serialization_alias="updatedAt")


class ConversationSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    notebook_id: str | None = Field(default=None, alias="notebookId", serialization_alias="notebookId")
    message_count: int = Field(default=0, alias="messageCount", serialization_alias="messageCount")
    created_at: str = Field(alias="createdAt", serialization_alias="createdAt")
    updated_at: str = Field(alias="updatedAt", serialization_alias="updatedAt")


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = "Cuộc hội thoại mới"
    notebook_id: str | None = Field(default=None, alias="notebookId")


class ConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=140)


class NoteItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    notebook_id: str | None = Field(default=None, alias="notebookId", serialization_alias="notebookId")
    title: str
    content: str
    note_type: NoteType = Field(default="pinned", alias="noteType", serialization_alias="noteType")
    source_document_ids: list[str] = Field(
        default_factory=list,
        alias="sourceDocumentIds",
        serialization_alias="sourceDocumentIds",
    )
    created_at: str = Field(default_factory=utc_now_iso, alias="createdAt", serialization_alias="createdAt")
    updated_at: str = Field(default_factory=utc_now_iso, alias="updatedAt", serialization_alias="updatedAt")


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    notebook_id: str | None = Field(default=None, alias="notebookId")
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)
    note_type: NoteType = Field(default="pinned", alias="noteType")
    source_document_ids: list[str] = Field(default_factory=list, alias="sourceDocumentIds")


class StudioGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: StudioGenerateType
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")
    notebook_id: str | None = Field(default=None, alias="notebookId")
    save_as_note: bool = Field(default=True, alias="saveAsNote")
    custom_instruction: str | None = Field(default=None, alias="customInstruction")


class StudioGenerateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    content: str
    type: StudioGenerateType
    generation_mode: Literal["llm", "extractive_fallback"] = Field(
        default="extractive_fallback",
        alias="generationMode",
        serialization_alias="generationMode",
    )
    model_used: str | None = Field(default=None, alias="modelUsed", serialization_alias="modelUsed")
    note: NoteItem | None = None


class SourceGuideResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(alias="documentId", serialization_alias="documentId")
    document_title: str = Field(alias="documentTitle", serialization_alias="documentTitle")
    summary: str
    key_topics: list[str] = Field(default_factory=list, alias="keyTopics", serialization_alias="keyTopics")
    suggested_questions: list[str] = Field(
        default_factory=list,
        alias="suggestedQuestions",
        serialization_alias="suggestedQuestions",
    )
    chunk_count: int = Field(default=0, alias="chunkCount", serialization_alias="chunkCount")
    generation_mode: Literal["llm", "extractive_fallback"] = Field(
        default="extractive_fallback",
        alias="generationMode",
        serialization_alias="generationMode",
    )
    model_used: str | None = Field(default=None, alias="modelUsed", serialization_alias="modelUsed")
