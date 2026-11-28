from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from src.config.settings import Settings
from src.ingestion.pipeline import IngestionPipeline
from src.llm.base import LLMProvider
from src.retrieval.service import RAGQueryService
from src.retrieval.studio import StudioService
from src.storage.kb_store import KnowledgeBaseStore
from src.storage.workspace_store import WorkspaceStore
from src.vectordb.base import VectorStore


@dataclass
class AppServices:
    settings: Settings
    kb_store: KnowledgeBaseStore
    vector_store: VectorStore
    workspace_store: WorkspaceStore
    llm_provider: LLMProvider
    pipeline: IngestionPipeline
    query_service: RAGQueryService
    studio_service: StudioService


def get_services(request: Request) -> AppServices:
    return request.app.state.services
