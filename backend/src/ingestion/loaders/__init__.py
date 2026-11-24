from __future__ import annotations

from pathlib import Path

from src.ingestion.loaders.base import BaseLoader
from src.ingestion.loaders.docx_loader import DocxLoader
from src.ingestion.loaders.pdf_loader import PdfLoader
from src.ingestion.loaders.text_loader import TextLoader
from src.schemas.chunk import ExtractedDocument
from src.schemas.document import DocumentFormat

_LOADERS: dict[DocumentFormat, BaseLoader] = {
    "PDF": PdfLoader(),
    "DOCX": DocxLoader(),
    "MD": TextLoader(),
    "TXT": TextLoader(),
}


def load_document(file_path: Path, fmt: DocumentFormat, title: str) -> ExtractedDocument:
    """Dispatch document extraction to the loader matching `fmt`."""
    loader = _LOADERS.get(fmt)
    if loader is None:
        raise ValueError(f"No loader registered for format '{fmt}'.")
    return loader.load(file_path, title=title, fmt=fmt)


__all__ = ["BaseLoader", "DocxLoader", "PdfLoader", "TextLoader", "load_document"]
