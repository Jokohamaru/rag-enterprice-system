from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.schemas.chunk import ExtractedDocument
from src.schemas.document import DocumentFormat


class BaseLoader(ABC):
    """Abstract document loader converting binary/text files into ExtractedDocument."""

    @abstractmethod
    def load(self, file_path: Path, *, title: str, fmt: DocumentFormat) -> ExtractedDocument:
        raise NotImplementedError
