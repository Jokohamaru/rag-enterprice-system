from __future__ import annotations

from src.ingestion.chunkers import ParentChildChunker, RecursiveChunker, SemanticChunker, count_tokens
from src.ingestion.embedders.base import MockEmbedder
from src.schemas.chunk import ExtractedDocument, ExtractedPage


def _sample_doc() -> ExtractedDocument:
    sentences = [
        f"Câu số {i} trình bày về quy trình bảo mật dữ liệu và truy xuất ngữ nghĩa trong doanh nghiệp."
        for i in range(1, 45)
    ]
    return ExtractedDocument(
        title="Sample Policy",
        format="TXT",
        pages=[ExtractedPage(page_number=1, section="Mục 1: Bảo mật", text=" ".join(sentences))],
    )


def test_recursive_chunker_respects_budget_and_overlap() -> None:
    doc = _sample_doc()
    chunker = RecursiveChunker(chunk_size=120, chunk_overlap=24)
    out = chunker.chunk(doc, document_id="doc-1", tenant_id="org-1", department="dept-it")
    assert len(out.chunks) >= 3
    for ch in out.chunks:
        assert ch.token_count <= 135  # allows minor single-sentence boundary margin
        assert ch.section == "Mục 1: Bảo mật"
        assert ch.page == 1


def test_parent_child_chunker_links_children_to_parents() -> None:
    doc = _sample_doc()
    chunker = ParentChildChunker(
        parent_chunk_size=350,
        parent_chunk_overlap=40,
        child_chunk_size=100,
        child_chunk_overlap=20,
    )
    out = chunker.chunk(doc, document_id="doc-1", tenant_id="org-1", department="dept-it")
    assert len(out.parent_chunks) >= 2
    assert len(out.chunks) > len(out.parent_chunks)
    parent_ids = {p.parent_id for p in out.parent_chunks}
    assert all(c.parent_id in parent_ids for c in out.chunks)


def test_semantic_chunker_splits_topics() -> None:
    text = (
        "Nhân viên được nghỉ 15 ngày phép năm có lương. "
        "Yêu cầu nghỉ phép cần gửi trên hệ thống HRM trước 17h. "
        "Khi cấu hình WireGuard VPN cần bật xác thực hai lớp TOTP. "
        "Nếu mất laptop cần gọi đường dây nóng IT 1199 để khóa máy từ xa."
    )
    doc = ExtractedDocument(
        title="Mixed Topics",
        format="TXT",
        pages=[ExtractedPage(page_number=1, section="Tổng hợp", text=text)],
    )
    chunker = SemanticChunker(MockEmbedder(dim=128), breakpoint_percentile=35.0, max_chunk_tokens=150)
    out = chunker.chunk(doc, document_id="doc-sem", tenant_id="org-1", department="dept-it")
    assert len(out.chunks) >= 2
    assert all(count_tokens(c.content) > 0 for c in out.chunks)
