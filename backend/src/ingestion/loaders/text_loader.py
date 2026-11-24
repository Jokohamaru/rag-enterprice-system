from __future__ import annotations

import re
from pathlib import Path

from src.ingestion.loaders.base import BaseLoader
from src.schemas.chunk import ExtractedDocument, ExtractedPage
from src.schemas.document import DocumentFormat

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class TextLoader(BaseLoader):
    """Extract Markdown or plain TXT files, splitting into logical sections by `#` headings."""

    def load(self, file_path: Path, *, title: str, fmt: DocumentFormat = "TXT") -> ExtractedDocument:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        if not raw.strip():
            raise ValueError(f"Text file '{file_path.name}' is empty.")

        sections: list[tuple[str, list[str]]] = []
        current_section = "Tổng quan"
        buffer: list[str] = []
        in_code_fence = False

        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                buffer.append(line)
                continue

            if fmt == "MD" and not in_code_fence:
                m = MD_HEADING_RE.match(stripped)
                if m:
                    if buffer and "\n".join(buffer).strip():
                        sections.append((current_section, buffer))
                        buffer = []
                    current_section = m.group(2).strip()
                    buffer.append(stripped)
                    continue
            buffer.append(line)

        if buffer and "\n".join(buffer).strip():
            sections.append((current_section, buffer))

        pages = [
            ExtractedPage(page_number=idx, section=sec, text="\n".join(lines).strip())
            for idx, (sec, lines) in enumerate(sections, start=1)
        ]

        if not pages:
            raise ValueError(f"Text file '{file_path.name}' contains no extractable content.")

        return ExtractedDocument(title=title, format=fmt, pages=pages)
