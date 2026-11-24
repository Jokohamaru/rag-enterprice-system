from __future__ import annotations

import re
from pathlib import Path

from src.ingestion.loaders.base import BaseLoader
from src.schemas.chunk import ExtractedDocument, ExtractedPage
from src.schemas.document import DocumentFormat

HEADING_LINE_RE = re.compile(
    r"^((?:[IVX]+|[0-9]+(?:\.[0-9]+)*)[.)]\s+.+|(?:Chương|Phần|Mục|Step|Section)\s+.+)$",
    re.IGNORECASE,
)


def _detect_section(text: str, current_section: str) -> str:
    for line in text.splitlines()[:12]:
        candidate = line.strip()
        if 3 <= len(candidate) <= 120 and HEADING_LINE_RE.match(candidate):
            return candidate
    return current_section


class PdfLoader(BaseLoader):
    """Extract text page-by-page from PDF using PyMuPDF (`fitz`) with `pypdf` fallback."""

    def load(self, file_path: Path, *, title: str, fmt: DocumentFormat = "PDF") -> ExtractedDocument:
        pages: list[ExtractedPage] = []
        current_section = "Trang 1"

        try:
            import pymupdf

            with pymupdf.open(file_path) as doc:
                for idx, page in enumerate(doc, start=1):
                    raw_text = page.get_text("text") or ""
                    if not raw_text.strip():
                        continue
                    current_section = _detect_section(raw_text, current_section if idx > 1 else f"Trang {idx}")
                    pages.append(
                        ExtractedPage(
                            page_number=idx,
                            section=current_section,
                            text=raw_text,
                        )
                    )
        except ImportError:
            from pypdf import PdfReader

            reader = PdfReader(str(file_path))
            for idx, page in enumerate(reader.pages, start=1):
                raw_text = page.extract_text() or ""
                if not raw_text.strip():
                    continue
                current_section = _detect_section(raw_text, current_section if idx > 1 else f"Trang {idx}")
                pages.append(
                    ExtractedPage(
                        page_number=idx,
                        section=current_section,
                        text=raw_text,
                    )
                )

        if not pages:
            raise ValueError(f"PDF '{file_path.name}' contains no extractable text.")

        return ExtractedDocument(title=title, format=fmt, pages=pages)
