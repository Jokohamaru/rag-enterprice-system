from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.llm.base import LLMMessage, LLMProvider, LLMResult
from src.main import create_app
from src.vectordb.memory_store import InMemoryVectorStore


class _StudioStubLLM(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "stub"

    @property
    def model_name(self) -> str:
        return "stub-studio"

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
        if json_mode:
            payload = {
                "summary": "Tài liệu quy định về bảo mật VPN và xử lý sự cố hạ tầng.",
                "overview": "Bộ tài liệu tổng hợp quy trình VPN và xử lý sự cố nội bộ.",
                "keyTopics": ["WireGuard VPN", "Xác thực 2 lớp", "Sev-1 SLA"],
                "suggestedQuestions": [
                    "Cấp quyền VPN mất bao lâu?",
                    "Sự cố Sev-1 phản hồi trong mấy phút?",
                ],
            }
            return LLMResult(text=json.dumps(payload, ensure_ascii=False), model=self.model_name, provider="stub")

        return LLMResult(
            text="### Tóm tắt\nTài liệu hướng dẫn cấp VPN trong 4 giờ [1].",
            model=self.model_name,
            provider="stub",
        )

    def stream_generate(self, messages: list[LLMMessage], *, temperature: float = 0.2, max_tokens: int = 2048):
        yield "Tài khoản WireGuard VPN được cấp trong 4 giờ [1]."


def test_notebooks_conversations_studio_and_source_guide_lifecycle(tmp_path: Path) -> None:
    settings = Settings(
        storage_dir=str(tmp_path / "storage"),
        embedding_provider="mock",
        gemini_embedding_dim=128,
        query_rewrite_enabled=False,
    )
    app = create_app(
        settings=settings,
        vector_store=InMemoryVectorStore(),
        llm_provider=_StudioStubLLM(),
    )
    client = TestClient(app)

    # 1. Upload document
    up = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "vpn_guide.md",
                b"# VPN Guide\nTai khoan WireGuard VPN duoc cap trong 4 gio lam viec va bat SSO + TOTP.",
                "text/markdown",
            )
        },
        data={"category": "Kỹ thuật & IT"},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    # 2. Source Guide
    guide_res = client.get(f"/api/v1/documents/{doc_id}/guide")
    assert guide_res.status_code == 200
    guide = guide_res.json()
    assert guide["documentId"] == doc_id
    assert guide["generationMode"] == "llm"
    assert "WireGuard VPN" in guide["keyTopics"]

    # 3. Create & manage Notebook + Overview
    nb_res = client.post(
        "/api/v1/notebooks",
        json={"title": "Sổ tay IT", "description": "Tài liệu vận hành IT", "documentIds": [doc_id]},
    )
    assert nb_res.status_code == 201
    nb_id = nb_res.json()["id"]

    ov_res = client.post(
        "/api/v1/notebooks/overview",
        json={"notebookId": nb_id, "documentIds": [doc_id]},
    )
    assert ov_res.status_code == 200
    assert ov_res.json()["generationMode"] == "llm"
    assert len(ov_res.json()["suggestedQuestions"]) >= 1

    # 4. Create Conversation and query with persistence
    conv_res = client.post(
        "/api/v1/conversations",
        json={"title": "Cuộc hội thoại mới", "notebookId": nb_id},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    q_res = client.post(
        "/api/v1/query",
        json={
            "question": "Cấp VPN mất bao lâu?",
            "notebookId": nb_id,
            "conversationId": conv_id,
            "topK": 3,
        },
    )
    assert q_res.status_code == 200
    assert q_res.json()["conversationId"] == conv_id

    conv_detail = client.get(f"/api/v1/conversations/{conv_id}").json()
    assert len(conv_detail["messages"]) == 2
    assert conv_detail["messages"][0]["role"] == "user"
    assert conv_detail["messages"][1]["role"] == "assistant"
    assert conv_detail["title"] == "Cấp VPN mất bao lâu?"

    # 5. Studio generation saves note automatically
    studio_res = client.post(
        "/api/v1/studio/generate",
        json={
            "type": "faq",
            "documentIds": [doc_id],
            "notebookId": nb_id,
            "saveAsNote": True,
        },
    )
    assert studio_res.status_code == 200
    studio_data = studio_res.json()
    assert studio_data["generationMode"] == "llm"
    assert studio_data["note"] is not None

    notes = client.get(f"/api/v1/notes?notebook_id={nb_id}").json()
    assert len(notes) == 1

    # 6. Manual note + cleanup deletes
    manual_note = client.post(
        "/api/v1/notes",
        json={"notebookId": nb_id, "title": "Ghi chú riêng", "content": "Cần bật TOTP", "noteType": "custom"},
    ).json()
    assert client.delete(f"/api/v1/notes/{manual_note['id']}").status_code == 200
    assert client.delete(f"/api/v1/conversations/{conv_id}").status_code == 200
    assert client.delete(f"/api/v1/notebooks/{nb_id}").status_code == 200
