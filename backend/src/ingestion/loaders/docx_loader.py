from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from src.ingestion.loaders.base import BaseLoader
from src.schemas.chunk import ExtractedDocument, ExtractedPage
from src.schemas.document import DocumentFormat


def _table_to_markdown(table: Table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    normalized = [r + [""] * (col_count - len(r)) for r in rows]
    lines = ["| " + " | ".join(normalized[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


class DocxLoader(BaseLoader):
    """Extract DOCX preserving reading order of headings, paragraphs, and Markdown tables."""

    def load(self, file_path: Path, *, title: str, fmt: DocumentFormat = "DOCX") -> ExtractedDocument:
        doc = DocxDocument(str(file_path))
        doc_title = title
        sections: list[tuple[str, list[str]]] = []
        current_section = "Tổng quan"
        buffer: list[str] = []

        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                para = Paragraph(child, doc)
                text = para.text.strip()
                if not text:
                    continue
                style_name = (para.style.name if para.style else "") or ""
                if style_name == "Title" and text:
                    doc_title = text
                    continue
                if style_name.startswith("Heading"):
                    if buffer:
                        sections.append((current_section, buffer))
                        buffer = []
                    current_section = text
                    buffer.append(text)
                else:
                    buffer.append(text)
            elif isinstance(child, CT_Tbl):
                table_md = _table_to_markdown(Table(child, doc))
                if table_md:
                    buffer.append(table_md)

        if buffer:
            sections.append((current_section, buffer))

        pages: list[ExtractedPage] = [
            ExtractedPage(page_number=idx, section=sec, text="\n\n".join(lines))
            for idx, (sec, lines) in enumerate(sections, start=1)
            if "\n".join(lines).strip()
        ]

        if not pages:
            raise ValueError(f"DOCX '{file_path.name}' contains no extractable text.")

        return ExtractedDocument(title=doc_title, format=fmt, pages=pages)
