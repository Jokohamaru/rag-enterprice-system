from __future__ import annotations

import unicodedata
from pathlib import Path

from docx import Document as DocxDocument

from src.ingestion.cleaner import TextCleaner
from src.ingestion.loaders import load_document
from src.schemas.chunk import ExtractedDocument, ExtractedPage

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def test_text_cleaner_normalizes_nfd_vietnamese_and_strips_repeated_pdf_headers() -> None:
    nfd_text = unicodedata.normalize("NFD", "Quy định bảo mật thông tin nội bộ")
    pages = [
        ExtractedPage(page_number=i, section="Mục 1", text=f"AI VIET NAM HEADER\n{nfd_text} trang {i}.\nTrang {i}/4")
        for i in range(1, 5)
    ]
    cleaned = TextCleaner().clean(ExtractedDocument(title="Test PDF", format="PDF", pages=pages))
    assert len(cleaned.pages) == 4
    for p in cleaned.pages:
        assert "AI VIET NAM HEADER" not in p.text
        assert unicodedata.is_normalized("NFC", p.text)


def test_markdown_and_txt_loaders(tmp_path: Path) -> None:
    md_file = tmp_path / "runbook.md"
    md_file.write_text("# Giới thiệu\nNội dung phần 1.\n\n## Xử lý sự cố\nChi tiết Sev-1.", encoding="utf-8")
    md_doc = load_document(md_file, fmt="MD", title="Runbook")
    assert len(md_doc.pages) == 2
    assert md_doc.pages[1].section == "Xử lý sự cố"

    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Ghi chú vận hành hàng ngày.", encoding="utf-8")
    txt_doc = load_document(txt_file, fmt="TXT", title="Notes")
    assert len(txt_doc.pages) == 1
    assert "Ghi chú vận hành" in txt_doc.pages[0].text


def test_docx_loader_preserves_tables_as_markdown(tmp_path: Path) -> None:
    docx_file = tmp_path / "policy.docx"
    d = DocxDocument()
    d.add_heading("Phân quyền truy cập", level=1)
    d.add_paragraph("Bảng phân quyền theo phòng ban:")
    tbl = d.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "Phòng ban"
    tbl.cell(0, 1).text = "Quyền"
    tbl.cell(1, 0).text = "dept-hr"
    tbl.cell(1, 1).text = "Chỉ đọc HR"
    d.save(str(docx_file))

    loaded = load_document(docx_file, fmt="DOCX", title="Policy")
    joined = "\n".join(p.text for p in loaded.pages)
    assert "| Phòng ban | Quyền |" in joined
    assert "| dept-hr | Chỉ đọc HR |" in joined


def test_real_workspace_pdf_and_docx_if_present() -> None:
    pdf_path = WORKSPACE_ROOT / "RAG_Architectures_A_Complete_Guide_for_2025.pdf"
    docx_path = WORKSPACE_ROOT / "Secure_multi_tenant_RAG_with_Amazon_Bedrock_and_Verified_Permissions.docx"
    if pdf_path.exists():
        pdf_doc = TextCleaner().clean(load_document(pdf_path, fmt="PDF", title="RAG Architectures 2025"))
        assert len(pdf_doc.pages) >= 5
        assert "Information Extraction" in "\n".join(p.text for p in pdf_doc.pages)
    if docx_path.exists():
        docx_doc = TextCleaner().clean(load_document(docx_path, fmt="DOCX", title="AWS Multi-Tenant RAG"))
        assert len(docx_doc.pages) >= 5
        assert any("|" in p.text for p in docx_doc.pages)
