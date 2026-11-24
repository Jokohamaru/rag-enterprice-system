from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from src.api.deps import AppServices, get_services
from src.schemas.chunk import ChunkRecord
from src.schemas.document import DocumentItem, DocumentUpdateRequest
from src.storage.kb_store import SidecarValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentItem])
def list_documents(
    tenant_id: str | None = Query(default=None),
    department: str | None = Query(default=None),
    services: AppServices = Depends(get_services),
) -> list[DocumentItem]:
    return services.vector_store.list_documents(tenant_id=tenant_id, department=department)


@router.post("/upload", response_model=DocumentItem, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("Kỹ thuật & IT"),
    tenant_id: str | None = Form(None),
    department: str | None = Form(None),
    access_groups: str | None = Form(None),
    services: AppServices = Depends(get_services),
) -> DocumentItem:
    content = await file.read()
    groups = (
        [g.strip() for g in access_groups.split(",") if g.strip()]
        if access_groups
        else None
    )
    try:
        return services.pipeline.ingest_uploaded_file(
            filename=file.filename or "document.txt",
            content=content,
            category=category,
            tenant_id=tenant_id,
            department=department,
            access_groups=groups,
        )
    except (ValueError, SidecarValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/{document_id}", response_model=DocumentItem)
def get_document(document_id: str, services: AppServices = Depends(get_services)) -> DocumentItem:
    doc = services.vector_store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


@router.get("/{document_id}/chunks", response_model=list[ChunkRecord])
def get_document_chunks(
    document_id: str,
    services: AppServices = Depends(get_services),
) -> list[ChunkRecord]:
    doc = services.vector_store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return services.vector_store.get_document_chunks(document_id)


@router.patch("/{document_id}", response_model=DocumentItem)
def update_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    services: AppServices = Depends(get_services),
) -> DocumentItem:
    updated = services.pipeline.toggle_document_enabled(document_id, payload.enabled)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return updated


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(document_id: str, services: AppServices = Depends(get_services)) -> dict:
    deleted = services.pipeline.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return {"deleted": True, "documentId": document_id}
