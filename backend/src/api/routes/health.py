from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps import AppServices, get_services

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(services: AppServices = Depends(get_services)) -> dict:
    db_status = services.vector_store.ping()
    return {
        "status": "ok" if db_status.get("ok") else "degraded",
        "embedding_provider": services.settings.embedding_provider,
        "chunking_strategy": services.settings.chunking_strategy,
        "contextual_mode": services.settings.contextual_mode,
        "vectordb": db_status,
        "stats": services.vector_store.stats(),
    }
