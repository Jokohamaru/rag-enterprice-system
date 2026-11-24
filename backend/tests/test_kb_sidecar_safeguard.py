from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config.settings import Settings
from src.ingestion.embedders.base import MockEmbedder
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.sparse_indexer import SparseBM25Index
from src.storage.kb_store import KnowledgeBaseStore, SidecarValidationError
from src.vectordb.memory_store import InMemoryVectorStore


def _make_pipeline(tmp_path: Path) -> IngestionPipeline:
    settings = Settings(
        storage_dir=str(tmp_path / "storage"),
        embedding_provider="mock",
        gemini_embedding_dim=128,
        chunk_size_tokens=120,
        chunk_overlap_tokens=20,
    )
    kb_store = KnowledgeBaseStore(settings.resolved_storage_dir)
    vector_store = InMemoryVectorStore()
    embedder = MockEmbedder(dim=128)
    bm25 = SparseBM25Index(settings.resolved_storage_dir / "bm25" / "index.json")
    return IngestionPipeline(
        settings=settings,
        kb_store=kb_store,
        vector_store=vector_store,
        embedder=embedder,
        bm25_index=bm25,
    )


def test_phase1_creates_sidecar_and_phase2_succeeds(tmp_path: Path) -> None:
    pipe = _make_pipeline(tmp_path)
    doc = pipe.ingest_uploaded_file(
        filename="chinh_sach_nghi_phep.md",
        content=b"# Chinh sach nghi phep\n\nNhan vien chinh thuc duoc huong 15 ngay phep nam.",
        category="Nhân sự",
        tenant_id="acme-vn",
    )
    assert doc.status == "ready"
    assert doc.department == "dept-hr"
    assert doc.chunk_count >= 1
    assert Path(doc.sidecar_path).exists()


def test_missing_sidecar_fails_closed_and_writes_dlq(tmp_path: Path) -> None:
    pipe = _make_pipeline(tmp_path)
    orphan = pipe.kb_store.kb_dir / "default-org" / "dept-it" / "doc-orphan" / "secret.txt"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("Unprotected secret document", encoding="utf-8")

    with pytest.raises(SidecarValidationError):
        pipe.ingest_from_kb_path(orphan)

    dlq_records = pipe.vector_store.list_dlq()
    assert len(dlq_records) == 1
    assert dlq_records[0].stage == "sidecar_safeguard"
    assert len(list(pipe.kb_store.dlq_dir.glob("*.json"))) == 1


def test_department_mismatch_between_folder_and_sidecar_blocked(tmp_path: Path) -> None:
    pipe = _make_pipeline(tmp_path)
    file_path, sidecar_path, _ = pipe.kb_store.stage_document(
        filename="ops.txt",
        content=b"Noi quy van hanh he thong.",
        category="Vận hành",
        tenant_id="default-org",
    )
    # Tamper sidecar department to differ from folder `dept-ops`
    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    raw["metadataAttributes"]["department"] = "dept-hr"
    sidecar_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(SidecarValidationError, match="Department mismatch"):
        pipe.ingest_from_kb_path(file_path)


def test_sync_skips_unchanged_content_hash(tmp_path: Path) -> None:
    pipe = _make_pipeline(tmp_path)
    pipe.ingest_uploaded_file(
        filename="guide.txt",
        content=b"Huong dan ket noi WireGuard VPN noi bo cong ty.",
        category="Kỹ thuật & IT",
    )
    job = pipe.sync_knowledge_base(force_reingest=False)
    assert job.processed_files == 1
    assert job.skipped_files == 1
    assert job.indexed_files == 0
