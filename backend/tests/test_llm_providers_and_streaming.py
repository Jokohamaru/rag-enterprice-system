from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.ingestion.embedders.gemini_embedder import (
    GeminiEmbedder,
    _extract_retry_delay_seconds,
)
from src.ingestion.embedders.openai_embedder import OpenAICompatibleEmbedder
from src.llm.base import LLMMessage, LLMProvider, LLMResult
from src.llm.factory import build_llm_provider
from src.llm.openai_provider import OpenAICompatibleLLMProvider
from src.main import create_app
from src.vectordb.memory_store import InMemoryVectorStore


class _StubLLMProvider(LLMProvider):
    def __init__(self, *, reply_text: str | None = None, fail: bool = False) -> None:
        self.calls: list[list[LLMMessage]] = []
        self._reply_text = reply_text
        self._fail = fail

    @property
    def provider_name(self) -> str:
        return "stub"

    @property
    def model_name(self) -> str:
        return "stub-notebooklm-model"

    @property
    def is_configured(self) -> bool:
        return True

    def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResult:
        self.calls.append(messages)
        if self._fail:
            raise RuntimeError("Simulated upstream timeout")
        # Query rewrite prompt returns a standalone search phrase
        if messages and "viết lại truy vấn" in messages[0].content.lower():
            return LLMResult(
                text="Chính sách ngày phép năm và làm việc từ xa",
                model=self.model_name,
                provider=self.provider_name,
            )
        text = self._reply_text or (
            "Nhân viên chính thức được hưởng **15 ngày phép năm** [1].\n\n"
            "<<<FOLLOW_UPS>>>\n"
            "- Điều kiện chuyển phép sang năm sau là gì?\n"
            "- Quy trình đăng ký làm việc từ xa ra sao?\n"
            "- Thử việc có được tính phép không?"
        )
        return LLMResult(text=text, model=self.model_name, provider=self.provider_name)

    def stream_generate(self, messages: list[LLMMessage], *, temperature: float = 0.2, max_tokens: int = 2048):
        self.calls.append(messages)
        if self._fail:
            raise RuntimeError("Simulated stream failure")
        full = self._reply_text or (
            "Nhân viên chính thức được hưởng **15 ngày phép năm** [1].\n\n"
            "<<<FOLLOW_UPS>>>\n"
            "- Điều kiện chuyển phép sang năm sau?\n"
            "- Quy trình đăng ký hybrid?"
        )
        for i in range(0, len(full), 15):
            yield full[i : i + 15]


def test_openai_compatible_provider_sync_and_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [3.0, 4.0, 0.0, 0.0]}]},
            )
        body = json.loads(request.content.decode("utf-8"))
        if body.get("stream"):
            sse = (
                'data: {"choices":[{"delta":{"content":"Xin "}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"chào [1]"}}]}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": "Trả lời từ OpenAI-compatible [1]"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            },
        )

    transport = httpx.MockTransport(handler)
    llm = OpenAICompatibleLLMProvider(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        transport=transport,
    )
    assert llm.is_configured is True
    res = llm.generate([LLMMessage(role="user", content="Xin chào")])
    assert "OpenAI-compatible" in res.text
    assert res.usage is not None and res.usage.total_tokens == 18

    streamed = "".join(llm.stream_generate([LLMMessage(role="user", content="Hi")]))
    assert streamed == "Xin chào [1]"

    embedder = OpenAICompatibleEmbedder(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="text-embedding-3-small",
        output_dimensionality=4,
        transport=transport,
    )
    vec = embedder.embed_query("test")
    assert len(vec) == 4
    assert abs(vec[0] - 0.6) < 1e-4


def test_local_ollama_url_requires_no_api_key() -> None:
    settings = Settings(
        llm_provider="openai_compatible",
        llm_base_url="http://localhost:11434/v1",
        llm_api_key="",
        llm_model="qwen2.5:14b",
        embedding_provider="mock",
    )
    provider = build_llm_provider(settings)
    assert provider.is_configured is True
    assert provider.model_name == "qwen2.5:14b"


def test_llm_runs_with_mock_embedder_and_multi_turn_streaming(tmp_path: Path) -> None:
    settings = Settings(
        storage_dir=str(tmp_path / "storage"),
        embedding_provider="mock",
        gemini_embedding_dim=128,
        reranker_provider="lexical",
        query_rewrite_enabled=True,
    )
    stub_llm = _StubLLMProvider()
    app = create_app(settings=settings, vector_store=InMemoryVectorStore(), llm_provider=stub_llm)
    client = TestClient(app)

    health = client.get("/api/v1/health").json()
    assert health["llm_provider"] == "stub"
    assert health["llm_model"] == "stub-notebooklm-model"
    assert health["llm_configured"] is True

    up = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "hr_leave.md",
                b"# Nghi phep\nNhan vien chinh thuc duoc huong 15 ngay phep nam co luong. "
                b"Duoc phep chuyen toi da 5 ngay sang quy I nam sau.\n\n"
                b"## Lam viec tu xa\nDang ky hybrid toi da 2 ngay moi tuan.",
                "text/markdown",
            )
        },
        data={"category": "Nhân sự"},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    # Multi-turn query triggers QueryRewriter + LLM answer even with embedding_provider="mock"
    q_res = client.post(
        "/api/v1/query",
        json={
            "question": "Thế còn chuyển sang năm sau thì sao?",
            "documentIds": [doc_id],
            "topK": 3,
            "history": [
                {"role": "user", "content": "Nhân viên được mấy ngày phép năm?"},
                {"role": "assistant", "content": "Được 15 ngày phép năm."},
            ],
        },
    )
    assert q_res.status_code == 200
    body = q_res.json()
    assert body["generationMode"] == "llm"
    assert body["modelUsed"] == "stub-notebooklm-model"
    assert body["rewrittenQuery"] == "Chính sách ngày phép năm và làm việc từ xa"
    assert "<<<FOLLOW_UPS>>>" not in body["answer"]
    assert len(body["followUpQuestions"]) == 3
    assert body["citations"][0]["usedInAnswer"] is True

    # Streaming SSE endpoint emits status -> citations -> delta -> done without leaking delimiter
    with client.stream(
        "POST",
        "/api/v1/query/stream",
        json={"question": "Phép năm bao nhiêu ngày?", "documentIds": [doc_id], "topK": 3},
    ) as stream_res:
        assert stream_res.status_code == 200
        raw_sse = "".join(stream_res.iter_text())

    assert "event: status" in raw_sse
    assert "event: citations" in raw_sse
    assert "event: delta" in raw_sse
    assert "event: done" in raw_sse
    assert "<<<FOLLOW_UPS>>>" not in raw_sse


def test_llm_failure_exposes_warning_and_extractive_fallback(tmp_path: Path) -> None:
    settings = Settings(
        storage_dir=str(tmp_path / "storage"),
        embedding_provider="mock",
        gemini_embedding_dim=128,
    )
    failing_llm = _StubLLMProvider(fail=True)
    app = create_app(settings=settings, vector_store=InMemoryVectorStore(), llm_provider=failing_llm)
    client = TestClient(app)

    up = client.post(
        "/api/v1/documents/upload",
        files={"file": ("it.md", b"# VPN\nWireGuard VPN cap trong 4 gio.", "text/markdown")},
        data={"category": "Kỹ thuật & IT"},
    )
    doc_id = up.json()["id"]

    res = client.post(
        "/api/v1/query",
        json={"question": "WireGuard VPN", "documentIds": [doc_id], "topK": 3},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["generationMode"] == "extractive_fallback"
    assert data["warning"] is not None and "Simulated upstream timeout" in data["warning"]


def test_gemini_embedder_respects_429_retry_delay(monkeypatch) -> None:
    err_msg = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, "
        "'message': 'Please retry in 17.178139927s.', 'details': [{'retryDelay': '17s'}]}}"
    )
    assert _extract_retry_delay_seconds(RuntimeError(err_msg)) == 17.178139927

    sleep_calls: list[float] = []
    monkeypatch.setattr("src.ingestion.embedders.gemini_embedder.time.sleep", lambda s: sleep_calls.append(s))

    embedder = GeminiEmbedder(api_key="AIza-test-key", output_dimensionality=4)

    class _FakeModels:
        def __init__(self) -> None:
            self.attempts = 0

        def embed_content(self, *, model, contents, config):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError(err_msg)

            class _Emb:
                values = [3.0, 4.0, 0.0, 0.0]

            class _Resp:
                embeddings = [_Emb()]

            return _Resp()

    fake_models = _FakeModels()
    embedder._client = type("_FakeClient", (), {"models": fake_models})()

    vecs = embedder.embed_texts(["Xin chào"])
    assert fake_models.attempts == 2
    assert len(sleep_calls) == 1
    assert abs(sleep_calls[0] - 18.678139927) < 1e-4
    assert len(vecs) == 1
    assert abs(vecs[0][0] - 0.6) < 1e-4
