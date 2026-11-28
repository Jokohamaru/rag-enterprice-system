from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import AppServices, get_services
from src.schemas.workspace import (
    NotebookCreateRequest,
    NotebookItem,
    NotebookOverviewRequest,
    NotebookOverviewResponse,
    NotebookUpdateRequest,
)

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.get("", response_model=list[NotebookItem])
def list_notebooks(services: AppServices = Depends(get_services)) -> list[NotebookItem]:
    return services.workspace_store.list_notebooks()


@router.post("", response_model=NotebookItem, status_code=status.HTTP_201_CREATED)
def create_notebook(
    payload: NotebookCreateRequest,
    services: AppServices = Depends(get_services),
) -> NotebookItem:
    return services.workspace_store.create_notebook(
        title=payload.title,
        description=payload.description,
        document_ids=payload.document_ids,
    )


@router.post("/overview", response_model=NotebookOverviewResponse)
def generate_notebook_overview(
    payload: NotebookOverviewRequest,
    services: AppServices = Depends(get_services),
) -> NotebookOverviewResponse:
    return services.studio_service.generate_overview(
        document_ids=payload.document_ids,
        notebook_id=payload.notebook_id,
    )


@router.get("/{notebook_id}", response_model=NotebookItem)
def get_notebook(notebook_id: str, services: AppServices = Depends(get_services)) -> NotebookItem:
    nb = services.workspace_store.get_notebook(notebook_id)
    if nb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found.")
    return nb


@router.patch("/{notebook_id}", response_model=NotebookItem)
def update_notebook(
    notebook_id: str,
    payload: NotebookUpdateRequest,
    services: AppServices = Depends(get_services),
) -> NotebookItem:
    updated = services.workspace_store.update_notebook(
        notebook_id,
        title=payload.title,
        description=payload.description,
        document_ids=payload.document_ids,
        overview=payload.overview,
        suggested_questions=payload.suggested_questions,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found.")
    return updated


@router.delete("/{notebook_id}", status_code=status.HTTP_200_OK)
def delete_notebook(notebook_id: str, services: AppServices = Depends(get_services)) -> dict:
    deleted = services.workspace_store.delete_notebook(notebook_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found.")
    return {"deleted": True, "notebookId": notebook_id}
