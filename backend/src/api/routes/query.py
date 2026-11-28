from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

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


@router.post("/query/stream")
def stream_query_knowledge_base(
    payload: QueryRequest,
    services: AppServices = Depends(get_services),
) -> StreamingResponse:
    def event_generator():
        for evt in services.query_service.stream_query(payload):
            event_name = evt.get("event", "message")
            data_json = json.dumps(evt.get("data", {}), ensure_ascii=False)
            yield f"event: {event_name}\ndata: {data_json}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
