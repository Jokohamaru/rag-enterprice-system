from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings
from src.ingestion.embedders.base import MockEmbedder
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.sparse_indexer import SparseBM25Index
from src.schemas.chunk import SearchFilter
from src.storage.kb_store import KnowledgeBaseStore
from src.vectordb.memory_store import InMemoryVectorStore


def _setup(tmp_path: Path) -> tuple[IngestionPipeline, InMemoryVectorStore, MockEmbedder]:
    settings = Settings(
        storage_dir=str(tmp_path / "storage"),
        embedding_provider="mock",
        gemini_embedding_dim=128,
        chunk_size_tokens=200,
        chunk_overlap_tokens=40,
        contextual_mode="header",
    )
    kb_store = KnowledgeBaseStore(settings.resolved_storage_dir)
    store = InMemoryVectorStore()
    embedder = MockEmbedder(dim=128)
    bm25 = SparseBM25Index(settings.resolved_storage_dir / "bm25" / "index.json")
    pipe = IngestionPipeline(
        settings=settings,
        kb_store=kb_store,
        vector_store=store,
        embedder=embedder,
        bm25_index=bm25,
    )
    return pipe, store, embedder


def test_department_isolation_and_fail_closed_filters(tmp_path: Path) -> None:
    pipe, store, embedder = _setup(tmp_path)

    hr_doc = pipe.ingest_uploaded_file(
        filename="hr_salary.txt",
        content=b"Bang luong va chinh sach thuong tet cua phong Nhan su danh cho noi bo HR.",
        category="Nhân sự",
        tenant_id="corp-1",
    )
    it_doc = pipe.ingest_uploaded_file(
        filename="it_vpn.txt",
        content=b"Huong dan cau hinh WireGuard VPN va khoa thiet bi MDM khi mat laptop.",
        category="Kỹ thuật & IT",
        tenant_id="corp-1",
    )

    q_vec = embedder.embed_query("WireGuard VPN MDM")

    # Fail-closed: missing tenant or empty departments/groups must return nothing
    assert store.vector_search(q_vec, search_filter=SearchFilter(tenant_id="corp-1")) == []
    assert store.vector_search(q_vec, search_filter=SearchFilter(tenant_id="", departments=["dept-it"])) == []

    # HR user searching for IT keywords gets zero IT chunks
    hr_hits = store.vector_search(
        q_vec,
        search_filter=SearchFilter(tenant_id="corp-1", departments=["dept-hr"]),
        top_k=5,
    )
    assert all(h.chunk.department == "dept-hr" for h in hr_hits)
    assert all(h.chunk.document_id != it_doc.id for h in hr_hits)

    # IT user finds the IT document
    it_hits = store.vector_search(
        q_vec,
        search_filter=SearchFilter(tenant_id="corp-1", departments=["dept-it"]),
        top_k=5,
    )
    assert len(it_hits) >= 1
    assert it_hits[0].chunk.document_id == it_doc.id

    # Disabling document hides it from retrieval immediately
    pipe.toggle_document_enabled(it_doc.id, False)
    assert (
        store.vector_search(
            q_vec,
            search_filter=SearchFilter(tenant_id="corp-1", departments=["dept-it"]),
        )
        == []
    )

    # Deleting document removes all chunks, files, and BM25 entries
    assert pipe.delete_document(hr_doc.id) is True
    assert store.get_document_chunks(hr_doc.id) == []
    assert not Path(hr_doc.storage_path).exists()
    assert not Path(hr_doc.sidecar_path).exists()


def test_contextual_header_enrichment(tmp_path: Path) -> None:
    pipe, store, _ = _setup(tmp_path)
    doc = pipe.ingest_uploaded_file(
        filename="sop.md",
        content=b"# Quy trinh Backup\nThuc hien snapshot du lieu hang ngay luc 02:00.",
        category="Vận hành",
        tenant_id="corp-1",
    )
    chunks = store.get_document_chunks(doc.id)
    assert len(chunks) == 1
    assert "[Tài liệu:" in chunks[0].contextual_content
    assert "dept-ops" in chunks[0].contextual_content
    assert "Thuc hien snapshot" in chunks[0].content
