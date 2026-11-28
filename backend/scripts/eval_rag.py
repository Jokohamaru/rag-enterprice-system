"""Quick RAG retrieval & grounding evaluation script.

Usage (offline in-memory benchmark):
    python scripts/eval_rag.py
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.config.settings import Settings
from src.ingestion.pipeline import IngestionPipeline, build_embedder
from src.ingestion.sparse_indexer import SparseBM25Index
from src.llm.base import NullLLMProvider
from src.retrieval.service import RAGQueryService
from src.schemas.query import QueryRequest
from src.storage.kb_store import KnowledgeBaseStore
from src.vectordb.memory_store import InMemoryVectorStore

BENCHMARK_DOCS = [
    (
        "chinh_sach_nghi_phep.md",
        "Nhân sự",
        "# Phép năm\nNhân viên chính thức được hưởng 15 ngày phép năm có lương, chuyển tối đa 5 ngày sang quý I.\n\n"
        "# Hybrid\nNhân viên được làm việc từ xa tối đa 2 ngày mỗi tuần (trừ thứ Hai).",
    ),
    (
        "hoan_ung_cong_tac.md",
        "Vận hành",
        "# Hoàn ứng\nHồ sơ hoàn ứng nộp trong 7 ngày làm việc kèm hóa đơn VAT. Giải ngân vào thứ Sáu.\n\n"
        "# Định mức\nKhách sạn tại Hà Nội và TP.HCM tối đa 1.800.000 VNĐ/đêm, phụ cấp ăn uống 350.000 VNĐ/ngày.",
    ),
    (
        "huong_dan_vpn_sev1.md",
        "Kỹ thuật & IT",
        "# WireGuard VPN\nTài khoản WireGuard VPN được cấp trong 4 giờ làm việc và yêu cầu bật SSO + TOTP.\n\n"
        "# Sự cố Sev-1\nSự cố Sev-1 cần xác nhận trong 10 phút và hoàn thành Post-mortem trong 48 giờ.",
    ),
]

EVAL_CASES = [
    ("Nhân viên chính thức có bao nhiêu ngày phép năm?", "chinh_sach_nghi_phep.md"),
    ("Định mức khách sạn công tác ở Hà Nội bao nhiêu tiền một đêm?", "hoan_ung_cong_tac.md"),
    ("Thời gian phản hồi sự cố Sev-1 và Post-mortem là bao lâu?", "huong_dan_vpn_sev1.md"),
    ("Xin cấp quyền WireGuard VPN mất bao lâu?", "huong_dan_vpn_sev1.md"),
]


def run_eval(top_k: int = 3) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            storage_dir=str(Path(tmp) / "storage"),
            embedding_provider="mock",
            llm_provider="none",
            gemini_embedding_dim=128,
            reranker_provider="lexical",
        )
        kb = KnowledgeBaseStore(settings.resolved_storage_dir)
        store = InMemoryVectorStore()
        embedder = build_embedder(settings)
        bm25 = SparseBM25Index(settings.resolved_storage_dir / "bm25" / "index.json")

        pipeline = IngestionPipeline(
            settings=settings,
            kb_store=kb,
            vector_store=store,
            embedder=embedder,
            bm25_index=bm25,
        )

        filename_to_doc_id: dict[str, str] = {}
        for filename, category, text in BENCHMARK_DOCS:
            doc = pipeline.ingest_uploaded_file(
                filename=filename,
                content=text.encode("utf-8"),
                category=category,
            )
            filename_to_doc_id[filename] = doc.id

        query_service = RAGQueryService(
            settings=settings,
            vector_store=store,
            embedder=embedder,
            bm25_index=bm25,
            llm_provider=NullLLMProvider(),
        )

        hits = 0
        total_latency = 0
        for question, expected_filename in EVAL_CASES:
            expected_id = filename_to_doc_id[expected_filename]
            res = query_service.query(QueryRequest(question=question, top_k=top_k))
            total_latency += res.latency_ms
            retrieved_ids = [c.document_id for c in res.citations]
            matched = expected_id in retrieved_ids
            if matched:
                hits += 1
            print(
                f"[{'PASS' if matched else 'FAIL'}] {question} -> top={res.citations[0].document_title if res.citations else 'NONE'} "
                f"({res.latency_ms}ms)"
            )

        recall = hits / len(EVAL_CASES)
        avg_ms = total_latency / len(EVAL_CASES)
        print(f"\nSummary: Recall@{top_k} = {recall:.2%} ({hits}/{len(EVAL_CASES)}), avg_latency = {avg_ms:.1f}ms")
        return 0 if hits == len(EVAL_CASES) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Enterprise RAG retrieval quality.")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    raise SystemExit(run_eval(top_k=args.top_k))
