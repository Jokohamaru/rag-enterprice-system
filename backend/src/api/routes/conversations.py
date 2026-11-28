from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import AppServices, get_services
from src.schemas.workspace import (
    ConversationCreateRequest,
    ConversationItem,
    ConversationSummary,
    ConversationUpdateRequest,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    notebook_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    services: AppServices = Depends(get_services),
) -> list[ConversationSummary]:
    return services.workspace_store.list_conversations(notebook_id=notebook_id, limit=limit)


@router.post("", response_model=ConversationItem, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreateRequest,
    services: AppServices = Depends(get_services),
) -> ConversationItem:
    return services.workspace_store.create_conversation(
        title=payload.title,
        notebook_id=payload.notebook_id,
    )


@router.get("/{conversation_id}", response_model=ConversationItem)
def get_conversation(
    conversation_id: str,
    services: AppServices = Depends(get_services),
) -> ConversationItem:
    conv = services.workspace_store.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conv


@router.patch("/{conversation_id}", response_model=ConversationItem)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    services: AppServices = Depends(get_services),
) -> ConversationItem:
    updated = services.workspace_store.update_conversation_title(conversation_id, payload.title)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return updated


@router.delete("/{conversation_id}", status_code=status.HTTP_200_OK)
def delete_conversation(
    conversation_id: str,
    services: AppServices = Depends(get_services),
) -> dict:
    deleted = services.workspace_store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return {"deleted": True, "conversationId": conversation_id}
