from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.schemas.chunk import ChunkRecord

TOKEN_RE = re.compile(r"[a-zA-Z0-9À-ỹ]+(?:[-_./][a-zA-Z0-9À-ỹ]+)*", re.UNICODE)


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize Vietnamese + technical codes (e.g., `Sev-1`, `Error`, `503`, `Điều 244`)."""
    nfc = unicodedata.normalize("NFC", text).lower()
    raw_tokens = TOKEN_RE.findall(nfc)
    # Include accent-stripped forms alongside accented forms for robust Vietnamese keyword matching
    nfd_no_marks = (
        unicodedata.normalize("NFD", nfc)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_tokens = TOKEN_RE.findall(nfd_no_marks)
    tokens = list(raw_tokens)
    for tok in ascii_tokens:
        if tok not in raw_tokens:
            tokens.append(tok)
    return tokens


class SparseBM25Index:
    """Maintains a local BM25 corpus synchronized by document_id for Hybrid Search readiness."""

    def __init__(self, index_path: Path | None = None) -> None:
        self.index_path = Path(index_path) if index_path else None
        # doc_id -> list of {"chunk_id", "tokens", "department", "tenant_id", "access_groups", "enabled"}
        self._docs: dict[str, list[dict]] = {}
        self._flat_entries: list[dict] = []
        self._bm25: BM25Okapi | None = None
        if self.index_path and self.index_path.exists():
            self._load()

    def upsert_document_chunks(self, document_id: str, chunks: list[ChunkRecord]) -> None:
        self._docs[document_id] = [
            {
                "chunk_id": c.id,
                "document_id": c.document_id,
                "tenant_id": c.tenant_id,
                "department": c.department,
                "access_groups": list(c.access_groups),
                "enabled": c.enabled,
                "tokens": tokenize_for_bm25(f"{c.document_title} {c.section} {c.content}"),
            }
            for c in chunks
        ]
        self._rebuild()
        self._save()

    def set_document_enabled(self, document_id: str, enabled: bool) -> None:
        if document_id in self._docs:
            for item in self._docs[document_id]:
                item["enabled"] = enabled
            self._rebuild()
            self._save()

    def delete_document(self, document_id: str) -> None:
        if document_id in self._docs:
            del self._docs[document_id]
            self._rebuild()
            self._save()

    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        departments: list[str] | None = None,
        access_groups: list[str] | None = None,
        document_ids: list[str] | None = None,
        only_enabled: bool = True,
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        if not tenant_id or (not departments and not access_groups):
            return []
        if self._bm25 is None or not self._flat_entries:
            return []

        q_tokens = tokenize_for_bm25(query)
        if not q_tokens:
            return []

        scores = self._bm25.get_scores(q_tokens)
        dept_set = set(departments or [])
        grp_set = set(access_groups or [])
        doc_set = set(document_ids or [])

        hits: list[tuple[str, float]] = []
        for idx, entry in enumerate(self._flat_entries):
            if entry["tenant_id"] != tenant_id:
                continue
            if only_enabled and not entry["enabled"]:
                continue
            if doc_set and entry["document_id"] not in doc_set:
                continue
            dept_ok = bool(dept_set and entry["department"] in dept_set)
            grp_ok = bool(grp_set and grp_set.intersection(entry["access_groups"]))
            if not (dept_ok or grp_ok):
                continue
            score = float(scores[idx])
            if score > 0.0:
                hits.append((entry["chunk_id"], score))

        hits.sort(key=lambda x: x[1], reverse=True)
        return hits[:top_k]

    def _rebuild(self) -> None:
        self._flat_entries = [entry for entries in self._docs.values() for entry in entries]
        if self._flat_entries:
            corpus = [e["tokens"] or ["_empty_"] for e in self._flat_entries]
            self._bm25 = BM25Okapi(corpus)
        else:
            self._bm25 = None

    def _save(self) -> None:
        if not self.index_path:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._docs, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index_path)

    def _load(self) -> None:
        if not self.index_path or not self.index_path.exists():
            return
        try:
            self._docs = json.loads(self.index_path.read_text(encoding="utf-8"))
            self._rebuild()
        except Exception:
            self._docs = {}
            self._rebuild()
