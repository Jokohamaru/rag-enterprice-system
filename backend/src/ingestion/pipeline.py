from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from src.config.settings import Settings
from src.ingestion.chunkers import BaseChunker, ParentChildChunker, RecursiveChunker, SemanticChunker
from src.ingestion.cleaner import TextCleaner
from src.ingestion.embedders import EmbeddingProvider, GeminiEmbedder, MockEmbedder
from src.ingestion.enricher import ChunkEnricher
from src.ingestion.loaders import load_document
from src.ingestion.sparse_indexer import SparseBM25Index
from src.schemas.chunk import DLQRecord, IngestionJobResult
from src.schemas.document import DocumentItem, MetadataAttributes
from src.storage.kb_store import KnowledgeBaseStore, SidecarValidationError, format_size_label
from src.vectordb.base import VectorStore

logger = logging.getLogger(__name__)


def _format_display_date(iso_ts: str | None = None) -> str:
    if iso_ts:
        try:
            dt = datetime.fromisoformat(iso_ts)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return datetime.now(timezone.utc).strftime("%d/%m/%Y")


def build_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "mock":
        return MockEmbedder(dim=settings.gemini_embedding_dim)
    return GeminiEmbedder(
        api_key=settings.gemini_api_key,
        model=settings.gemini_embedding_model,
        output_dimensionality=settings.gemini_embedding_dim,
    )


def build_chunker(settings: Settings, embedder: EmbeddingProvider) -> BaseChunker:
    if settings.chunking_strategy == "parent_child":
        return ParentChildChunker(
            parent_chunk_size=settings.parent_chunk_size_tokens,
            parent_chunk_overlap=settings.parent_chunk_overlap_tokens,
            child_chunk_size=settings.child_chunk_size_tokens,
            child_chunk_overlap=settings.child_chunk_overlap_tokens,
        )
    if settings.chunking_strategy == "semantic":
        return SemanticChunker(
            embedder=embedder,
            breakpoint_percentile=settings.semantic_breakpoint_percentile,
            max_chunk_tokens=settings.chunk_size_tokens,
        )
    return RecursiveChunker(
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
    )


class IngestionPipeline:
    """End-to-end orchestrator: KB Storage -> Sidecar Safeguard -> Load/Clean/Chunk/Embed -> Vector DB."""

    def __init__(
        self,
        *,
        settings: Settings,
        kb_store: KnowledgeBaseStore,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        bm25_index: SparseBM25Index,
        cleaner: TextCleaner | None = None,
        chunker: BaseChunker | None = None,
        enricher: ChunkEnricher | None = None,
    ) -> None:
        self.settings = settings
        self.kb_store = kb_store
        self.vector_store = vector_store
        self.embedder = embedder
        self.bm25_index = bm25_index
        self.cleaner = cleaner or TextCleaner()
        self.chunker = chunker or build_chunker(settings, embedder)
        self.enricher = enricher or ChunkEnricher(
            contextual_mode=settings.contextual_mode,
            gemini_api_key=settings.gemini_api_key,
            gemini_context_model=settings.gemini_context_model,
        )

    def ingest_uploaded_file(
        self,
        *,
        filename: str,
        content: bytes,
        category: str,
        tenant_id: str | None = None,
        department: str | None = None,
        access_groups: list[str] | None = None,
        document_id: str | None = None,
        title: str | None = None,
    ) -> DocumentItem:
        """Phase 1 staging + immediate Phase 2 indexing for uploaded documents."""
        tenant = (tenant_id or self.settings.default_tenant_id).strip()
        try:
            file_path, sidecar_path, sidecar = self.kb_store.stage_document(
                filename=filename,
                content=content,
                category=category,
                tenant_id=tenant,
                department=department,
                access_groups=access_groups,
                document_id=document_id,
                title=title,
            )
        except Exception as exc:
            self._record_dlq(
                file_path=filename,
                stage="staging",
                error=str(exc),
                tenant_id=tenant,
                department=department,
            )
            raise

        return self.ingest_from_kb_path(file_path, force_reingest=True)

    def ingest_from_kb_path(self, file_path: Path, *, force_reingest: bool = False) -> DocumentItem:
        """Phase 2: Enforce `.metadata.json` safeguard, then extract, clean, chunk, embed, and index."""
        file_path = Path(file_path)
        sidecar_path = self.kb_store.sidecar_path_for(file_path)

        try:
            sidecar = self.kb_store.validate_sidecar(file_path)
        except SidecarValidationError as exc:
            self._record_dlq(
                file_path=str(file_path),
                stage="sidecar_safeguard",
                error=str(exc),
            )
            raise

        meta: MetadataAttributes = sidecar.metadataAttributes
        size_label = format_size_label(file_path.stat().st_size)

        # Idempotent skip if unchanged content_hash is already ready in DB
        existing = self.vector_store.get_document(meta.document_id)
        if (
            not force_reingest
            and existing is not None
            and existing.status == "ready"
            and existing.content_hash == meta.content_hash
        ):
            return existing

        doc_item = DocumentItem(
            id=meta.document_id,
            title=meta.title,
            filename=file_path.name,
            format=meta.format,
            category=meta.category,
            size_label=size_label,
            chunk_count=0,
            updated_at=_format_display_date(meta.updated_at),
            status="chunking",
            enabled=existing.enabled if existing else True,
            summary="",
            tenant_id=meta.tenant_id,
            department=meta.department,
            access_groups=list(meta.access_groups),
            content_hash=meta.content_hash,
            version=meta.version,
            storage_path=str(file_path),
            sidecar_path=str(sidecar_path),
        )
        self.vector_store.upsert_document(doc_item)

        stage: Literal["loading", "chunking", "embedding", "indexing"] = "loading"
        try:
            extracted = load_document(file_path, fmt=meta.format, title=meta.title)
            cleaned = self.cleaner.clean(extracted)

            stage = "chunking"
            chunk_out = self.chunker.chunk(
                cleaned,
                document_id=meta.document_id,
                tenant_id=meta.tenant_id,
                department=meta.department,
            )
            enriched_chunks = self.enricher.enrich(
                chunk_out.chunks,
                meta=meta,
                doc_summary=cleaned.summary,
                enabled=doc_item.enabled,
            )

            stage = "embedding"
            doc_item = doc_item.model_copy(
                update={"status": "embedding", "title": cleaned.title, "summary": cleaned.summary}
            )
            self.vector_store.upsert_document(doc_item)

            texts_to_embed = [c.contextual_content or c.content for c in enriched_chunks]
            vectors = self.embedder.embed_texts(texts_to_embed, task_type="RETRIEVAL_DOCUMENT")
            if len(vectors) != len(enriched_chunks):
                raise RuntimeError(
                    f"Embedding count mismatch: got {len(vectors)} vectors for {len(enriched_chunks)} chunks."
                )
            for chunk_rec, vec in zip(enriched_chunks, vectors):
                chunk_rec.embedding = vec

            stage = "indexing"
            self.vector_store.replace_document_chunks(
                meta.document_id,
                enriched_chunks,
                parent_chunks=chunk_out.parent_chunks,
            )
            self.bm25_index.upsert_document_chunks(meta.document_id, enriched_chunks)

            ready_doc = doc_item.model_copy(
                update={
                    "status": "ready",
                    "chunk_count": len(enriched_chunks),
                    "error_message": None,
                }
            )
            self.vector_store.upsert_document(ready_doc)
            return ready_doc
        except Exception as exc:
            err_doc = doc_item.model_copy(update={"status": "error", "error_message": str(exc)})
            self.vector_store.upsert_document(err_doc)
            self._record_dlq(
                file_path=str(file_path),
                stage=stage,
                error=str(exc),
                document_id=meta.document_id,
                tenant_id=meta.tenant_id,
                department=meta.department,
            )
            raise

    def sync_knowledge_base(
        self,
        *,
        force_reingest: bool = False,
        trigger: Literal["upload", "sync", "cli"] = "sync",
    ) -> IngestionJobResult:
        """Scan Knowledge Base directory and run Phase 2 ingestion for every valid staged file."""
        job_id = f"job-{uuid.uuid4().hex[:10]}"
        started_at = datetime.now(timezone.utc).isoformat()
        files = self.kb_store.scan_knowledge_base()

        indexed = 0
        skipped = 0
        failed = 0
        total_chunks = 0
        doc_ids: list[str] = []
        errors: list[str] = []

        for file_path in files:
            try:
                existing = None
                try:
                    sidecar = self.kb_store.validate_sidecar(file_path)
                    existing = self.vector_store.get_document(sidecar.metadataAttributes.document_id)
                    if (
                        not force_reingest
                        and existing is not None
                        and existing.status == "ready"
                        and existing.content_hash == sidecar.metadataAttributes.content_hash
                    ):
                        skipped += 1
                        doc_ids.append(existing.id)
                        total_chunks += existing.chunk_count
                        continue
                except SidecarValidationError:
                    pass

                doc = self.ingest_from_kb_path(file_path, force_reingest=force_reingest)
                indexed += 1
                total_chunks += doc.chunk_count
                doc_ids.append(doc.id)
            except Exception as exc:
                failed += 1
                errors.append(f"{file_path.name}: {exc}")

        status: Literal["completed", "partial", "failed"] = "completed"
        if failed > 0 and indexed == 0 and skipped == 0:
            status = "failed"
        elif failed > 0:
            status = "partial"

        job = IngestionJobResult(
            job_id=job_id,
            trigger=trigger,
            status=status,
            processed_files=len(files),
            indexed_files=indexed,
            skipped_files=skipped,
            failed_files=failed,
            total_chunks=total_chunks,
            document_ids=doc_ids,
            errors=errors,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        self.vector_store.record_job(job)
        return job

    def toggle_document_enabled(self, document_id: str, enabled: bool) -> DocumentItem | None:
        updated = self.vector_store.set_document_enabled(document_id, enabled)
        if updated is not None:
            self.bm25_index.set_document_enabled(document_id, enabled)
        return updated

    def delete_document(self, document_id: str) -> bool:
        doc = self.vector_store.get_document(document_id)
        if doc is not None:
            self.kb_store.delete_document_files(doc.storage_path, doc.sidecar_path)
        self.bm25_index.delete_document(document_id)
        return self.vector_store.delete_document(document_id)

    def _record_dlq(
        self,
        *,
        file_path: str,
        stage: Literal["staging", "sidecar_safeguard", "loading", "chunking", "embedding", "indexing"],
        error: str,
        document_id: str | None = None,
        tenant_id: str | None = None,
        department: str | None = None,
    ) -> None:
        record = DLQRecord(
            dlq_id=f"dlq-{uuid.uuid4().hex[:12]}",
            file_path=file_path,
            document_id=document_id,
            tenant_id=tenant_id,
            department=department,
            stage=stage,
            error=error,
        )
        self.kb_store.write_dlq_file(record)
        self.vector_store.record_dlq(record)
        logger.warning("DLQ [%s] %s: %s", stage, file_path, error)
