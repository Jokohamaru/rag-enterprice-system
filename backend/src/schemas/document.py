from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentFormat = Literal["PDF", "DOCX", "MD", "TXT"]
DocumentStatus = Literal["ready", "chunking", "embedding", "error"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetadataAttributes(BaseModel):
    """Authorization and provenance metadata stored in `.metadata.json` sidecar."""

    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(min_length=1)
    department: str = Field(min_length=1)
    category: str = Field(min_length=1)
    access_groups: list[str] = Field(min_length=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    format: DocumentFormat
    content_hash: str = Field(min_length=16)
    version: int = Field(default=1, ge=1)
    updated_at: str = Field(default_factory=utc_now_iso)


class MetadataSidecar(BaseModel):
    """Sidecar schema matching AWS Bedrock `.metadata.json` convention."""

    model_config = ConfigDict(populate_by_name=True)

    metadataAttributes: MetadataAttributes


class DocumentItem(BaseModel):
    """Document representation aligned with `frontend/src/types/rag.ts`."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    filename: str
    format: DocumentFormat
    category: str
    size_label: str = Field(alias="sizeLabel", serialization_alias="sizeLabel")
    chunk_count: int = Field(default=0, alias="chunkCount", serialization_alias="chunkCount")
    updated_at: str = Field(alias="updatedAt", serialization_alias="updatedAt")
    status: DocumentStatus
    enabled: bool = True
    summary: str = ""

    # Multi-tenant & provenance fields
    tenant_id: str = "default-org"
    department: str = "dept-general"
    access_groups: list[str] = Field(default_factory=list)
    content_hash: str = ""
    version: int = 1
    storage_path: str = ""
    sidecar_path: str = ""
    error_message: str | None = None


class DocumentUpdateRequest(BaseModel):
    """Payload to enable/disable a document in the shared Knowledge Base."""

    enabled: bool
