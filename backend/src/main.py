from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.deps import AppServices
from src.api.routes import documents_router, health_router, ingestion_router
from src.config.settings import Settings, get_settings
from src.ingestion.pipeline import IngestionPipeline, build_embedder
from src.ingestion.sparse_indexer import SparseBM25Index
from src.storage.kb_store import KnowledgeBaseStore
from src.vectordb.base import VectorStore
from src.vectordb.mongodb_store import MongoDBVectorStore


def build_services(
    settings: Settings,
    *,
    vector_store: VectorStore | None = None,
) -> AppServices:
    kb_store = KnowledgeBaseStore(
        storage_dir=settings.resolved_storage_dir,
        max_file_size_mb=settings.max_file_size_mb,
    )
    store = vector_store or MongoDBVectorStore(
        uri=settings.mongodb_uri,
        db_name=settings.mongodb_db_name,
        vector_mode=settings.mongodb_vector_mode,
        embedding_dim=settings.gemini_embedding_dim,
    )
    store.ensure_indexes()
    embedder = build_embedder(settings)
    bm25 = SparseBM25Index(settings.resolved_storage_dir / "bm25" / "index.json")
    pipeline = IngestionPipeline(
        settings=settings,
        kb_store=kb_store,
        vector_store=store,
        embedder=embedder,
        bm25_index=bm25,
    )
    return AppServices(
        settings=settings,
        kb_store=kb_store,
        vector_store=store,
        pipeline=pipeline,
    )


def create_app(
    settings: Settings | None = None,
    *,
    vector_store: VectorStore | None = None,
) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not hasattr(application.state, "services") or application.state.services is None:
            application.state.services = build_services(cfg, vector_store=vector_store)
        yield

    application = FastAPI(
        title="Enterprise RAG Ingestion & Vector DB API",
        version="0.1.0",
        lifespan=lifespan,
    )
    if vector_store is not None:
        application.state.services = build_services(cfg, vector_store=vector_store)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router, prefix="/api/v1")
    application.include_router(documents_router, prefix="/api/v1")
    application.include_router(ingestion_router, prefix="/api/v1")
    return application


app = create_app()
