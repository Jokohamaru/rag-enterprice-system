from __future__ import annotations

import logging
import re
import time

from src.ingestion.embedders.base import EmbeddingProvider, TaskType, l2_normalize

logger = logging.getLogger(__name__)

_RETRY_IN_RE = re.compile(r"retry in\s+(\d+(?:\.\d+)?)s", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.IGNORECASE)


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).upper()
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _extract_retry_delay_seconds(exc: Exception) -> float | None:
    msg = str(exc)
    for pattern in (_RETRY_IN_RE, _RETRY_DELAY_RE):
        match = pattern.search(msg)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


class GeminiEmbedder(EmbeddingProvider):
    """Google Gemini Bi-Encoder embedder using `google-genai` with batching and backoff."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-embedding-001",
        output_dimensionality: int = 768,
        batch_size: int = 50,
        max_retries: int = 6,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "GEMINI_API_KEY is missing. Set it in .env or switch EMBEDDING_PROVIDER=mock for offline testing."
            )
        from google import genai

        self._client = genai.Client(api_key=api_key.strip())
        self._model = model
        self._dim = output_dimensionality
        self._batch_size = batch_size
        self._max_retries = max_retries

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: list[str], *, task_type: TaskType = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        if not texts:
            return []

        from google.genai import types

        all_vectors: list[list[float]] = []
        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self._dim,
        )

        for start in range(0, len(texts), self._batch_size):
            batch = [t if t.strip() else " " for t in texts[start : start + self._batch_size]]
            response = self._embed_batch_with_retry(batch, config)
            for emb in response.embeddings or []:
                all_vectors.append(l2_normalize(list(emb.values)))
        return all_vectors

    def _embed_batch_with_retry(self, batch: list[str], config):
        delay = 1.0
        last_exc: Exception | None = None
        non_rate_limit_cap = min(self._max_retries, 3)

        for attempt in range(1, self._max_retries + 1):
            try:
                return self._client.models.embed_content(
                    model=self._model,
                    contents=batch,
                    config=config,
                )
            except Exception as exc:
                last_exc = exc
                is_429 = _is_rate_limit_error(exc)
                max_attempts = self._max_retries if is_429 else non_rate_limit_cap
                if attempt >= max_attempts:
                    break

                if is_429:
                    parsed = _extract_retry_delay_seconds(exc)
                    wait_s = min(max((parsed + 1.5) if parsed is not None else max(delay, 15.0), 1.0), 65.0)
                    logger.warning(
                        "Gemini embed rate-limited (429) on attempt %d/%d; waiting %.1fs before retry...",
                        attempt,
                        max_attempts,
                        wait_s,
                    )
                    time.sleep(wait_s)
                    delay = max(delay * 2.0, wait_s)
                else:
                    logger.warning("Gemini embed batch attempt %d/%d failed: %s", attempt, max_attempts, exc)
                    time.sleep(delay)
                    delay *= 2.0
        raise RuntimeError(f"Gemini embedding failed after {self._max_retries} attempts: {last_exc}") from last_exc
