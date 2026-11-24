from __future__ import annotations

import re
import unicodedata
from collections import Counter

from src.schemas.chunk import ExtractedDocument, ExtractedPage

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\ufeff]")
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
PAGE_NUMBER_ONLY_RE = re.compile(r"^(?:page|trang)?\s*\d+(?:\s*/\s*\d+)?$", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Normalize Vietnamese Unicode to NFC and clean PDF/DOCX extraction artifacts."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL_CHARS_RE.sub("", text)
    # Fix soft hyphenation across line breaks in PDFs
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    lines = [MULTI_SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(lines)
    cleaned = MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()


class TextCleaner:
    """Cleans extracted pages and strips repeated headers/footers across multi-page PDFs."""

    def clean(self, doc: ExtractedDocument) -> ExtractedDocument:
        normalized_pages: list[ExtractedPage] = []
        for p in doc.pages:
            cleaned = normalize_text(p.text)
            if cleaned:
                normalized_pages.append(
                    ExtractedPage(
                        page_number=p.page_number,
                        section=normalize_text(p.section) or f"Trang {p.page_number}",
                        text=cleaned,
                    )
                )

        if doc.format == "PDF" and len(normalized_pages) >= 3:
            normalized_pages = self._strip_repeated_headers_footers(normalized_pages)

        summary = self._build_summary(normalized_pages)
        return ExtractedDocument(
            title=normalize_text(doc.title) or doc.title,
            format=doc.format,
            pages=normalized_pages,
            summary=summary,
        )

    @staticmethod
    def _strip_repeated_headers_footers(pages: list[ExtractedPage]) -> list[ExtractedPage]:
        edge_counts: Counter[str] = Counter()
        for p in pages:
            lines = [ln.strip() for ln in p.text.splitlines() if ln.strip()]
            if not lines:
                continue
            candidates = {lines[0], lines[-1]}
            if len(lines) > 2:
                candidates.add(lines[1])
            for c in candidates:
                if len(c) <= 100:
                    edge_counts[c] += 1

        threshold = max(3, int(len(pages) * 0.6))
        noise_lines = {line for line, cnt in edge_counts.items() if cnt >= threshold}

        cleaned_pages: list[ExtractedPage] = []
        for p in pages:
            lines = p.text.splitlines()
            filtered: list[str] = []
            for idx, ln in enumerate(lines):
                s = ln.strip()
                is_edge = idx <= 1 or idx >= len(lines) - 2
                if is_edge and (s in noise_lines or PAGE_NUMBER_ONLY_RE.match(s)):
                    continue
                filtered.append(ln)
            body = MULTI_NEWLINE_RE.sub("\n\n", "\n".join(filtered)).strip()
            if body:
                cleaned_pages.append(
                    ExtractedPage(page_number=p.page_number, section=p.section, text=body)
                )
        return cleaned_pages or pages

    @staticmethod
    def _build_summary(pages: list[ExtractedPage], max_chars: int = 240) -> str:
        joined = " ".join(p.text.replace("\n", " ") for p in pages[:2])
        joined = MULTI_SPACE_RE.sub(" ", joined).strip()
        if len(joined) <= max_chars:
            return joined
        return joined[: max_chars - 3].rsplit(" ", 1)[0] + "..."
