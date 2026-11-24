from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.config.settings import Settings, get_settings
from src.ingestion.pipeline import IngestionPipeline, build_embedder
from src.ingestion.sparse_indexer import SparseBM25Index
from src.storage.kb_store import KnowledgeBaseStore
from src.vectordb.memory_store import InMemoryVectorStore
from src.vectordb.mongodb_store import MongoDBVectorStore


def create_pipeline(settings: Settings, *, in_memory: bool = False) -> IngestionPipeline:
    kb_store = KnowledgeBaseStore(
        storage_dir=settings.resolved_storage_dir,
        max_file_size_mb=settings.max_file_size_mb,
    )
    if in_memory:
        vector_store = InMemoryVectorStore()
    else:
        vector_store = MongoDBVectorStore(
            uri=settings.mongodb_uri,
            db_name=settings.mongodb_db_name,
            vector_mode=settings.mongodb_vector_mode,
            embedding_dim=settings.gemini_embedding_dim,
        )
    vector_store.ensure_indexes()
    embedder = build_embedder(settings)
    bm25 = SparseBM25Index(settings.resolved_storage_dir / "bm25" / "index.json")
    return IngestionPipeline(
        settings=settings,
        kb_store=kb_store,
        vector_store=vector_store,
        embedder=embedder,
        bm25_index=bm25,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enterprise RAG Data Ingestion CLI")
    parser.add_argument("--memory", action="store_true", help="Use InMemoryVectorStore instead of MongoDB")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Stage and ingest one or more source files")
    p_ingest.add_argument("files", nargs="+", help="Paths to PDF, DOCX, MD, or TXT files")
    p_ingest.add_argument("--category", default="Kỹ thuật & IT", help="Document category")
    p_ingest.add_argument("--tenant", default=None, help="Tenant identifier")
    p_ingest.add_argument("--department", default=None, help="Explicit department override (e.g., dept-it)")

    p_sync = sub.add_parser("sync", help="Run Phase 2 batch sync on Knowledge Base directory")
    p_sync.add_argument("--force", action="store_true", help="Re-ingest even if content_hash is unchanged")

    sub.add_parser("stats", help="Print Knowledge Base and Vector DB statistics")

    args = parser.parse_args(argv)
    settings = get_settings()
    pipeline = create_pipeline(settings, in_memory=args.memory)

    if args.command == "ingest":
        results = []
        for f in args.files:
            p = Path(f)
            if not p.exists():
                print(f"[ERROR] File not found: {p}", file=sys.stderr)
                return 1
            doc = pipeline.ingest_uploaded_file(
                filename=p.name,
                content=p.read_bytes(),
                category=args.category,
                tenant_id=args.tenant,
                department=args.department,
            )
            results.append(doc.model_dump(by_alias=True))
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync":
        job = pipeline.sync_knowledge_base(force_reingest=args.force, trigger="cli")
        print(json.dumps(job.model_dump(), ensure_ascii=False, indent=2))
        return 0 if job.failed_files == 0 else 1

    if args.command == "stats":
        print(json.dumps(pipeline.vector_store.stats(), ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
