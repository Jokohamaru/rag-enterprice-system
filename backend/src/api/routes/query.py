from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import AppServices, get_services
from src.schemas.query import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query_knowledge_base(
    payload: QueryRequest,
    services: AppServices = Depends(get_services),
) -> QueryResponse:
    try:
        return services.query_service.query(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
