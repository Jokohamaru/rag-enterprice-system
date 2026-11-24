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

    # 1. Health endpoint + CORS check for Vite default 127.0.0.1:5173
    health = client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"

    preflight = client.options(
        "/api/v1/query",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"

    # 2. Upload document matching frontend FormData (`file`, `category`)
    upload = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "sop_bao_mat.md",
                b"# Bao mat\nKhong chia se mat khau VPN WireGuard qua chat noi bo.",
                "text/markdown",
            )
        },
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

    # 5. Query endpoint matches frontend QueryResponse & CitationItem contract
    empty_scope = client.post("/api/v1/query", json={"question": "VPN", "documentIds": [], "topK": 3})
    assert empty_scope.status_code == 200
    assert empty_scope.json()["citations"] == []

    query_res = client.post(
        "/api/v1/query",
        json={"question": "Quy dinh mat khau VPN WireGuard?", "documentIds": [doc_id], "topK": 3},
    )
    assert query_res.status_code == 200
    q_data = query_res.json()
    assert isinstance(q_data["answer"], str) and q_data["answer"]
    assert isinstance(q_data["latencyMs"], int) and q_data["latencyMs"] >= 1
    assert len(q_data["citations"]) >= 1
    cit = q_data["citations"][0]
    for key in (
        "id",
        "documentId",
        "documentTitle",
        "category",
        "section",
        "chunkIndex",
        "content",
        "citationNumber",
        "score",
    ):
        assert key in cit
    assert cit["documentId"] == doc_id
    assert cit["citationNumber"] == 1
    assert 0.0 <= cit["score"] <= 1.0

    # 6. Toggle enabled state and verify disabled documents are excluded from query
    patched = client.patch(f"/api/v1/documents/{doc_id}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    disabled_query = client.post(
        "/api/v1/query",
        json={"question": "VPN WireGuard", "documentIds": [doc_id], "topK": 3},
    )
    assert disabled_query.status_code == 200
    assert disabled_query.json()["citations"] == []

    # 7. Sync KB endpoint
    synced = client.post("/api/v1/ingestion/sync")
    assert synced.status_code == 200
    assert synced.json()["skipped_files"] == 1

    # 8. Delete document
    deleted = client.delete(f"/api/v1/documents/{doc_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
