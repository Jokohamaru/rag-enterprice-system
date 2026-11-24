from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.deps import AppServices, get_services
from src.schemas.chunk import DLQRecord, IngestionJobResult

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync", response_model=IngestionJobResult)
def sync_knowledge_base(
    force: bool = Query(default=False),
    services: AppServices = Depends(get_services),
) -> IngestionJobResult:
    return services.pipeline.sync_knowledge_base(force_reingest=force, trigger="sync")


@router.get("/jobs", response_model=list[IngestionJobResult])
def list_ingestion_jobs(
    limit: int = Query(default=20, ge=1, le=200),
    services: AppServices = Depends(get_services),
) -> list[IngestionJobResult]:
    return services.vector_store.list_jobs(limit=limit)


@router.get("/dlq", response_model=list[DLQRecord])
def list_dlq_events(
    limit: int = Query(default=50, ge=1, le=200),
    services: AppServices = Depends(get_services),
) -> list[DLQRecord]:
    return services.vector_store.list_dlq(limit=limit)
