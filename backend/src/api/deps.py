from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from src.config.settings import Settings
from src.ingestion.pipeline import IngestionPipeline
from src.storage.kb_store import KnowledgeBaseStore
from src.vectordb.base import VectorStore


@dataclass
class AppServices:
    settings: Settings
    kb_store: KnowledgeBaseStore
    vector_store: VectorStore
    pipeline: IngestionPipeline


def get_services(request: Request) -> AppServices:
    return request.app.state.services
