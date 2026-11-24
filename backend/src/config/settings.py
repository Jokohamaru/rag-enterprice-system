from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT_DIR = BACKEND_DIR.parent

CATEGORY_DEPARTMENT_MAP: dict[str, str] = {
    "Nhân sự": "dept-hr",
    "Vận hành": "dept-ops",
    "Kỹ thuật & IT": "dept-it",
}


def category_to_department(category: str) -> str:
    """Map human-readable category labels to normalized department identifiers."""
    clean = unicodedata.normalize("NFC", category.strip())
    if clean in CATEGORY_DEPARTMENT_MAP:
        return CATEGORY_DEPARTMENT_MAP[clean]
    ascii_slug = (
        unicodedata.normalize("NFD", clean)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_slug).strip("-")
    return f"dept-{slug}" if slug else "dept-general"


class Settings(BaseSettings):
    """Application settings loaded from backend/.env with fallback to root .env."""

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Embedding & LLM (Google Gemini)
    gemini_api_key: str = ""
    embedding_provider: Literal["gemini", "mock"] = "gemini"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = Field(default=768, ge=64, le=3072)
    gemini_context_model: str = "gemini-2.0-flash"
    gemini_generation_model: str = "gemini-2.0-flash"

    # MongoDB Vector Database
    mongodb_uri: str = "mongodb://admin:password123@localhost:27017/?authSource=admin"
    mongodb_db_name: str = "rag_enterprise"
    mongodb_vector_mode: Literal["auto", "atlas", "community"] = "auto"

    # Knowledge Base & Storage
    storage_dir: str = "storage"
    default_tenant_id: str = "default-org"
    max_file_size_mb: int = Field(default=50, ge=1, le=500)

    # Chunking & Contextual Retrieval
    chunking_strategy: Literal["recursive", "parent_child", "semantic"] = "recursive"
    chunk_size_tokens: int = Field(default=400, ge=50, le=4000)
    chunk_overlap_tokens: int = Field(default=80, ge=0, le=1000)
    parent_chunk_size_tokens: int = Field(default=1000, ge=200, le=8000)
    parent_chunk_overlap_tokens: int = Field(default=100, ge=0, le=1000)
    child_chunk_size_tokens: int = Field(default=250, ge=50, le=2000)
    child_chunk_overlap_tokens: int = Field(default=50, ge=0, le=500)
    semantic_breakpoint_percentile: float = Field(default=20.0, gt=0.0, lt=100.0)
    contextual_mode: Literal["header", "llm"] = "header"

    # API
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"

    @property
    def resolved_storage_dir(self) -> Path:
        path = Path(self.storage_dir)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
