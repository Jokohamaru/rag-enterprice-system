from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app
from src.vectordb.memory_store import InMemoryVectorStore


def test_fastapi_ingestion_lifecycle_matches_frontend_contract(tmp_path: Path) -> None:
    settings = Settings(
        storage_dir=str(tmp_path / "storage"),
        embedding_provider="mock",
        gemini_embedding_dim=128,
        chunk_size_tokens=200,
        chunk_overlap_tokens=40,
    )
    app = create_app(settings=settings, vector_store=InMemoryVectorStore())
    client = TestClient(app)

    # 1. Health endpoint
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # 2. Upload document matching frontend FormData (`file`, `category`)
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sop_bao_mat.md", b"# Bao mat\nKhong chia se mat khau qua chat.", "text/markdown")},
        data={"category": "Kỹ thuật & IT"},
    )
    assert upload.status_code == 201
    doc = upload.json()
    # Verify camelCase serialization matching `frontend/src/types/rag.ts`
    for key in ("id", "title", "filename", "format", "category", "sizeLabel", "chunkCount", "updatedAt", "status", "enabled"):
        assert key in doc
    assert doc["status"] == "ready"
    assert doc["chunkCount"] >= 1
    assert doc["department"] == "dept-it"

    doc_id = doc["id"]

    # 3. List documents
    listed = client.get("/api/v1/documents")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # 4. Inspect indexed chunks
    chunks = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks.status_code == 200
    chunk_list = chunks.json()
    assert len(chunk_list) == doc["chunkCount"]
    assert "documentId" in chunk_list[0]
    assert "chunkIndex" in chunk_list[0]

    # 5. Toggle enabled state
    patched = client.patch(f"/api/v1/documents/{doc_id}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    # 6. Sync KB endpoint
    synced = client.post("/api/v1/ingestion/sync")
    assert synced.status_code == 200
    assert synced.json()["skipped_files"] == 1

    # 7. Delete document
    deleted = client.delete(f"/api/v1/documents/{doc_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
