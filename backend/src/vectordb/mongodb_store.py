from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from src.schemas.chunk import ChunkRecord, DLQRecord, IngestionJobResult, ParentChunk, SearchFilter, SearchResult
from src.schemas.document import DocumentItem
from src.vectordb.base import VectorStore, is_filter_authorized

logger = logging.getLogger(__name__)

VECTOR_INDEX_NAME = "chunks_vector_index"
TEXT_INDEX_NAME = "chunks_atlas_text_index"


class MongoDBVectorStore(VectorStore):
    """Dual-mode MongoDB VectorStore supporting Community (`mongo:latest`) and Atlas (`$vectorSearch`)."""

    def __init__(
        self,
        *,
        uri: str,
        db_name: str = "rag_enterprise",
        vector_mode: Literal["auto", "atlas", "community"] = "auto",
        embedding_dim: int = 768,
        server_selection_timeout_ms: int = 5000,
    ) -> None:
        self.uri = uri
        self.db_name = db_name
        self.configured_mode = vector_mode
        self.active_vector_mode: Literal["atlas", "community"] = (
            "atlas" if vector_mode == "atlas" else "community"
        )
        self.embedding_dim = embedding_dim
        self.client = MongoClient(uri, serverSelectionTimeoutMS=server_selection_timeout_ms)
        self.db = self.client[db_name]

        self.documents_col = self.db["documents"]
        self.parents_col = self.db["parent_chunks"]
        self.chunks_col = self.db["chunks"]
        self.jobs_col = self.db["ingestion_jobs"]
        self.dlq_col = self.db["dlq_events"]

    def ensure_indexes(self) -> None:
        """Create standard compound/text indexes and probe Atlas Search index support if configured."""
        self.documents_col.create_index([("id", ASCENDING)], unique=True)
        self.documents_col.create_index([("tenant_id", ASCENDING), ("department", ASCENDING), ("updated_at", DESCENDING)])

        self.parents_col.create_index([("parent_id", ASCENDING)], unique=True)
        self.parents_col.create_index([("document_id", ASCENDING), ("chunk_index", ASCENDING)])

        self.chunks_col.create_index([("id", ASCENDING)], unique=True)
        self.chunks_col.create_index(
            [
                ("tenant_id", ASCENDING),
                ("department", ASCENDING),
                ("enabled", ASCENDING),
                ("document_id", ASCENDING),
            ],
            name="idx_isolation_prefilter",
        )
        self.chunks_col.create_index([("access_groups", ASCENDING)], name="idx_access_groups")
        self.chunks_col.create_index([("document_id", ASCENDING), ("chunk_index", ASCENDING)], name="idx_doc_chunk")
        self.chunks_col.create_index(
            [("content", TEXT), ("section", TEXT), ("document_title", TEXT)],
            name="idx_chunks_text",
            default_language="none",
        )

        self.jobs_col.create_index([("job_id", ASCENDING)], unique=True)
        self.jobs_col.create_index([("started_at", DESCENDING)])
        self.dlq_col.create_index([("dlq_id", ASCENDING)], unique=True)
        self.dlq_col.create_index([("created_at", DESCENDING)])

        if self.configured_mode == "community":
            self.active_vector_mode = "community"
            return

        # Probe Atlas Search ($vectorSearch) support on the connected MongoDB deployment
        try:
            existing = {idx.get("name") for idx in self.chunks_col.list_search_indexes()}
            if VECTOR_INDEX_NAME not in existing:
                vector_model = SearchIndexModel(
                    definition={
                        "fields": [
                            {
                                "type": "vector",
                                "path": "embedding",
                                "numDimensions": self.embedding_dim,
                                "similarity": "cosine",
                            },
                            {"type": "filter", "path": "tenant_id"},
                            {"type": "filter", "path": "department"},
                            {"type": "filter", "path": "category"},
                            {"type": "filter", "path": "document_id"},
                            {"type": "filter", "path": "enabled"},
                            {"type": "filter", "path": "access_groups"},
                        ]
                    },
                    name=VECTOR_INDEX_NAME,
                    type="vectorSearch",
                )
                self.chunks_col.create_search_index(model=vector_model)

            if TEXT_INDEX_NAME not in existing:
                text_model = SearchIndexModel(
                    definition={
                        "mappings": {
                            "dynamic": False,
                            "fields": {
                                "content": {"type": "string"},
                                "section": {"type": "string"},
                                "document_title": {"type": "string"},
                                "tenant_id": {"type": "token"},
                                "department": {"type": "token"},
                                "document_id": {"type": "token"},
                                "enabled": {"type": "boolean"},
                                "access_groups": {"type": "token"},
                            },
                        }
                    },
                    name=TEXT_INDEX_NAME,
                    type="search",
                )
                self.chunks_col.create_search_index(model=text_model)

            self.active_vector_mode = "atlas"
            logger.info("MongoDB Atlas Vector Search indexes verified/created.")
        except OperationFailure as exc:
            if self.configured_mode == "atlas":
                raise RuntimeError(
                    "MONGODB_VECTOR_MODE=atlas requested, but the connected MongoDB server does not support Atlas Search indexes."
                ) from exc
            self.active_vector_mode = "community"
            logger.info("Connected to MongoDB Community; using compound pre-filter + NumPy cosine mode (%s).", exc)

    def ping(self) -> dict:
        res = self.client.admin.command("ping")
        return {
            "ok": bool(res.get("ok") == 1),
            "backend": "mongodb",
            "database": self.db_name,
            "vector_mode": self.active_vector_mode,
        }

    def upsert_document(self, doc: DocumentItem) -> None:
        payload = doc.model_dump(mode="json", by_alias=False)
        self.documents_col.replace_one({"id": doc.id}, payload, upsert=True)

    def get_document(self, document_id: str) -> DocumentItem | None:
        raw = self.documents_col.find_one({"id": document_id}, {"_id": 0})
        return DocumentItem.model_validate(raw) if raw else None

    def list_documents(self, *, tenant_id: str | None = None, department: str | None = None) -> list[DocumentItem]:
        query: dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if department:
            query["department"] = department
        cursor = self.documents_col.find(query, {"_id": 0}).sort("updated_at", DESCENDING)
        return [DocumentItem.model_validate(row) for row in cursor]

    def set_document_enabled(self, document_id: str, enabled: bool) -> DocumentItem | None:
        doc = self.get_document(document_id)
        if doc is None:
            return None
        self.documents_col.update_one({"id": document_id}, {"$set": {"enabled": enabled}})
        self.chunks_col.update_many({"document_id": document_id}, {"$set": {"enabled": enabled}})
        return doc.model_copy(update={"enabled": enabled})

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[ChunkRecord],
        parent_chunks: list[ParentChunk] | None = None,
    ) -> None:
        self.chunks_col.delete_many({"document_id": document_id})
        self.parents_col.delete_many({"document_id": document_id})

        if parent_chunks:
            self.parents_col.insert_many([p.model_dump(mode="json", by_alias=False) for p in parent_chunks])
        if chunks:
            self.chunks_col.insert_many([c.model_dump(mode="json", by_alias=False) for c in chunks])

    def get_document_chunks(self, document_id: str) -> list[ChunkRecord]:
        cursor = self.chunks_col.find({"document_id": document_id}, {"_id": 0, "embedding": 0}).sort(
            "chunk_index", ASCENDING
        )
        return [ChunkRecord.model_validate(row) for row in cursor]

    def get_parent_chunk(self, parent_id: str) -> ParentChunk | None:
        raw = self.parents_col.find_one({"parent_id": parent_id}, {"_id": 0})
        return ParentChunk.model_validate(raw) if raw else None

    def delete_document(self, document_id: str) -> bool:
        doc_res = self.documents_col.delete_one({"id": document_id})
        chk_res = self.chunks_col.delete_many({"document_id": document_id})
        self.parents_col.delete_many({"document_id": document_id})
        return doc_res.deleted_count > 0 or chk_res.deleted_count > 0

    @staticmethod
    def _build_mongo_prefilter(flt: SearchFilter) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if not flt.allow_unscoped_admin:
            query["tenant_id"] = flt.tenant_id
            or_clauses: list[dict[str, Any]] = []
            depts = [d.strip() for d in flt.departments if d.strip()]
            groups = [g.strip() for g in flt.access_groups if g.strip()]
            if depts:
                or_clauses.append({"department": {"$in": depts}})
            if groups:
                or_clauses.append({"access_groups": {"$in": groups}})
            if len(or_clauses) == 1:
                query.update(or_clauses[0])
            elif len(or_clauses) > 1:
                query["$or"] = or_clauses

        if flt.only_enabled:
            query["enabled"] = True
        doc_ids = [d.strip() for d in flt.document_ids if d.strip()]
        if doc_ids:
            query["document_id"] = {"$in": doc_ids}
        return query

    def vector_search(
        self,
        query_vector: list[float],
        *,
        search_filter: SearchFilter,
        top_k: int = 5,
        num_candidates: int = 100,
    ) -> list[SearchResult]:
        if not is_filter_authorized(search_filter) or not query_vector:
            return []

        if self.active_vector_mode == "atlas":
            return self._atlas_vector_search(
                query_vector,
                search_filter=search_filter,
                top_k=top_k,
                num_candidates=num_candidates,
            )
        return self._community_vector_search(query_vector, search_filter=search_filter, top_k=top_k)

    def _atlas_vector_search(
        self,
        query_vector: list[float],
        *,
        search_filter: SearchFilter,
        top_k: int,
        num_candidates: int,
    ) -> list[SearchResult]:
        # Atlas MQL $vectorSearch filter syntax
        and_filters: list[dict[str, Any]] = []
        if not search_filter.allow_unscoped_admin:
            and_filters.append({"tenant_id": {"$eq": search_filter.tenant_id}})
            depts = [d.strip() for d in search_filter.departments if d.strip()]
            if depts:
                and_filters.append({"department": {"$in": depts}})
            groups = [g.strip() for g in search_filter.access_groups if g.strip()]
            if groups and not depts:
                and_filters.append({"access_groups": {"$in": groups}})
        if search_filter.only_enabled:
            and_filters.append({"enabled": {"$eq": True}})
        doc_ids = [d.strip() for d in search_filter.document_ids if d.strip()]
        if doc_ids:
            and_filters.append({"document_id": {"$in": doc_ids}})

        atlas_filter: dict[str, Any] = {"$and": and_filters} if len(and_filters) > 1 else (and_filters[0] if and_filters else {})
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(num_candidates, top_k * 10),
                    "limit": top_k,
                    **({"filter": atlas_filter} if atlas_filter else {}),
                }
            },
            {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "vectorSearchScore"}}},
        ]
        results: list[SearchResult] = []
        for row in self.chunks_col.aggregate(pipeline):
            score = float(row.pop("score", 0.0))
            results.append(SearchResult(chunk=ChunkRecord.model_validate(row), score=score, source="vector"))
        return results

    def _community_vector_search(
        self,
        query_vector: list[float],
        *,
        search_filter: SearchFilter,
        top_k: int,
    ) -> list[SearchResult]:
        mongo_filter = self._build_mongo_prefilter(search_filter)
        rows = list(self.chunks_col.find(mongo_filter, {"_id": 0}))
        if not rows:
            return []

        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = float(np.linalg.norm(q))
        if q_norm > 1e-12:
            q = q / q_norm

        valid_rows: list[dict[str, Any]] = []
        vecs: list[list[float]] = []
        for row in rows:
            emb = row.pop("embedding", None)
            if emb and len(emb) == len(query_vector):
                valid_rows.append(row)
                vecs.append(emb)

        if not valid_rows:
            return []

        mat = np.asarray(vecs, dtype=np.float32)
        scores = mat @ q
        ranked_idx = np.argsort(-scores)[:top_k]
        return [
            SearchResult(
                chunk=ChunkRecord.model_validate(valid_rows[int(i)]),
                score=float(scores[int(i)]),
                source="vector",
            )
            for i in ranked_idx
        ]

    def keyword_search(
        self,
        query_text: str,
        *,
        search_filter: SearchFilter,
        top_k: int = 5,
    ) -> list[SearchResult]:
        if not is_filter_authorized(search_filter) or not query_text.strip():
            return []
        mongo_filter = self._build_mongo_prefilter(search_filter)
        mongo_filter["$text"] = {"$search": query_text}
        cursor = (
            self.chunks_col.find(
                mongo_filter,
                {"_id": 0, "embedding": 0, "score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(top_k)
        )
        out: list[SearchResult] = []
        for row in cursor:
            score = float(row.pop("score", 0.0))
            out.append(SearchResult(chunk=ChunkRecord.model_validate(row), score=score, source="keyword"))
        return out

    def record_job(self, job: IngestionJobResult) -> None:
        payload = job.model_dump(mode="json")
        self.jobs_col.replace_one({"job_id": job.job_id}, payload, upsert=True)

    def list_jobs(self, limit: int = 20) -> list[IngestionJobResult]:
        cursor = self.jobs_col.find({}, {"_id": 0}).sort("started_at", DESCENDING).limit(limit)
        return [IngestionJobResult.model_validate(row) for row in cursor]

    def record_dlq(self, record: DLQRecord) -> None:
        payload = record.model_dump(mode="json")
        self.dlq_col.replace_one({"dlq_id": record.dlq_id}, payload, upsert=True)

    def list_dlq(self, limit: int = 50) -> list[DLQRecord]:
        cursor = self.dlq_col.find({}, {"_id": 0}).sort("created_at", DESCENDING).limit(limit)
        return [DLQRecord.model_validate(row) for row in cursor]

    def stats(self) -> dict:
        pipeline = [{"$group": {"_id": "$department", "count": {"$sum": 1}}}]
        by_dept = {row["_id"]: row["count"] for row in self.chunks_col.aggregate(pipeline) if row.get("_id")}
        return {
            "backend": "mongodb",
            "database": self.db_name,
            "vector_mode": self.active_vector_mode,
            "documents": self.documents_col.count_documents({}),
            "chunks": self.chunks_col.count_documents({}),
            "parent_chunks": self.parents_col.count_documents({}),
            "dlq_events": self.dlq_col.count_documents({}),
            "chunks_by_department": by_dept,
        }
