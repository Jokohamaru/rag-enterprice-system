from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import httpx

from src.ingestion.embedders.base import EmbeddingProvider, TaskType, l2_normalize

logger = logging.getLogger(__name__)


def _is_local_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local")


class OpenAICompatibleEmbedder(EmbeddingProvider):
    """Embedding adapter for OpenAI, OpenRouter, Ollama, and vLLM `/embeddings` APIs."""

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        output_dimensionality: int = 768,
        batch_size: int = 50,
        max_retries: int = 3,
        timeout_seconds: float = 45.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = (base_url.strip() or "https://api.openai.com/v1").rstrip("/")
        if not self._api_key and not _is_local_url(self._base_url):
            raise ValueError(
                "EMBEDDING_API_KEY is missing for OpenAI-compatible embedder. "
                "Set it in .env or switch EMBEDDING_PROVIDER=mock."
            )
        self._model = model.strip() or "text-embedding-3-small"
        self._dim = output_dimensionality
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: list[str], *, task_type: TaskType = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        client_kwargs: dict = {"timeout": self._timeout_seconds}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        url = f"{self._base_url}/embeddings"
        all_vectors: list[list[float]] = []

        with httpx.Client(**client_kwargs) as client:
            for start in range(0, len(texts), self._batch_size):
                batch = [t if t.strip() else " " for t in texts[start : start + self._batch_size]]
                payload: dict = {"model": self._model, "input": batch}
                if self._model.startswith("text-embedding-3"):
                    payload["dimensions"] = self._dim

                data = self._post_with_retry(client, url, headers, payload)
                items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
                for item in items:
                    vec = l2_normalize(list(item.get("embedding") or []))
                    all_vectors.append(vec)

        return all_vectors

    def _post_with_retry(self, client: httpx.Client, url: str, headers: dict, payload: dict) -> dict:
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < self._max_retries:
                    time.sleep(delay)
                    delay *= 2.0
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    break
                logger.warning("OpenAI-compatible embed attempt %d/%d failed: %s", attempt, self._max_retries, exc)
                time.sleep(delay)
                delay *= 2.0
        raise RuntimeError(f"OpenAI-compatible embedding failed: {last_exc}") from last_exc
