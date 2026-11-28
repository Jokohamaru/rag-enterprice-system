from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import AppServices, get_services
from src.schemas.workspace import (
    NoteCreateRequest,
    NoteItem,
    StudioGenerateRequest,
    StudioGenerateResponse,
)

router = APIRouter(tags=["studio"])


@router.post("/studio/generate", response_model=StudioGenerateResponse)
def generate_studio_artifact(
    payload: StudioGenerateRequest,
    services: AppServices = Depends(get_services),
) -> StudioGenerateResponse:
    return services.studio_service.generate_studio_artifact(payload)


@router.get("/notes", response_model=list[NoteItem])
def list_notes(
    notebook_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    services: AppServices = Depends(get_services),
) -> list[NoteItem]:
    return services.workspace_store.list_notes(notebook_id=notebook_id, limit=limit)


@router.post("/notes", response_model=NoteItem, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreateRequest,
    services: AppServices = Depends(get_services),
) -> NoteItem:
    return services.workspace_store.create_note(
        title=payload.title,
        content=payload.content,
        note_type=payload.note_type,
        notebook_id=payload.notebook_id,
        source_document_ids=payload.source_document_ids,
    )


@router.delete("/notes/{note_id}", status_code=status.HTTP_200_OK)
def delete_note(
    note_id: str,
    services: AppServices = Depends(get_services),
) -> dict:
    deleted = services.workspace_store.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
    return {"deleted": True, "noteId": note_id}
