from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from urllib.parse import urlparse

import httpx

from src.llm.base import LLMMessage, LLMProvider, LLMResult, LLMUsage

logger = logging.getLogger(__name__)


def _is_local_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local")


class OpenAICompatibleLLMProvider(LLMProvider):
    """Adapter for OpenAI, OpenRouter, Groq, DeepSeek, Ollama, vLLM, and LM Studio."""

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 45.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = (base_url.strip() or "https://api.openai.com/v1").rstrip("/")
        self._model = model.strip() or "gpt-4o-mini"
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._transport = transport

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key) or _is_local_url(self._base_url)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_client(self) -> httpx.Client:
        kwargs: dict = {"timeout": self._timeout_seconds}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResult:
        if not self.is_configured:
            raise RuntimeError("LLM_API_KEY is missing for OpenAICompatibleLLMProvider.")

        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self._base_url}/chat/completions"
        delay = 1.0
        last_exc: Exception | None = None

        with self._build_client() as client:
            for attempt in range(1, self._max_retries + 1):
                try:
                    resp = client.post(url, headers=self._headers(), json=payload)
                    if resp.status_code in {429, 500, 502, 503, 504} and attempt < self._max_retries:
                        logger.warning(
                            "OpenAI-compatible API HTTP %d on attempt %d/%d",
                            resp.status_code,
                            attempt,
                            self._max_retries,
                        )
                        time.sleep(delay)
                        delay *= 2.0
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices") or []
                    text = ""
                    if choices:
                        message_obj = choices[0].get("message") or {}
                        content = message_obj.get("content", "")
                        if isinstance(content, str):
                            text = content.strip()
                        elif isinstance(content, list):
                            text = "".join(
                                str(part.get("text", ""))
                                for part in content
                                if isinstance(part, dict)
                            ).strip()
                    usage_raw = data.get("usage")
                    usage = (
                        LLMUsage(
                            prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
                            completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
                            total_tokens=int(usage_raw.get("total_tokens", 0) or 0),
                        )
                        if isinstance(usage_raw, dict)
                        else None
                    )
                    return LLMResult(
                        text=text,
                        model=str(data.get("model") or self._model),
                        provider=self.provider_name,
                        usage=usage,
                    )
                except Exception as exc:
                    last_exc = exc
                    if attempt == self._max_retries:
                        break
                    time.sleep(delay)
                    delay *= 2.0

        raise RuntimeError(f"OpenAI-compatible generation failed: {last_exc}") from last_exc

    def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Iterator[str]:
        if not self.is_configured:
            raise RuntimeError("LLM_API_KEY is missing for OpenAICompatibleLLMProvider.")

        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        url = f"{self._base_url}/chat/completions"

        with self._build_client() as client:
            with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    stripped = line.strip()
                    if not stripped.startswith("data:"):
                        continue
                    data_str = stripped[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if isinstance(piece, str) and piece:
                        yield piece
