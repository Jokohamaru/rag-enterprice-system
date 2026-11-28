from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator

from src.llm.base import LLMMessage, LLMProvider, LLMResult, LLMUsage

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


class GeminiLLMProvider(LLMProvider):
    """Google Gemini LLM adapter built on `google-genai` with retry and streaming."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = 45.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model.strip() or "gemini-2.5-flash"
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if not self.is_configured:
            raise RuntimeError("GEMINI_API_KEY / LLM_API_KEY is missing for GeminiLLMProvider.")
        if self._client is None:
            from google import genai
            from google.genai import types

            http_opts = types.HttpOptions(timeout=int(self._timeout_seconds * 1000))
            self._client = genai.Client(api_key=self._api_key, http_options=http_opts)
        return self._client

    @staticmethod
    def _build_payload(
        messages: list[LLMMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ):
        from google.genai import types

        system_parts: list[str] = []
        contents: list[types.Content] = []
        for msg in messages:
            text = msg.content.strip()
            if not text:
                continue
            if msg.role == "system":
                system_parts.append(text)
            else:
                role = "model" if msg.role == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))

        if not contents:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=" ")]))

        config_kwargs: dict = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        return contents, types.GenerateContentConfig(**config_kwargs)

    def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResult:
        client = self._get_client()
        contents, config = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

        delay = 1.0
        last_exc: Exception | None = None
        rate_limit_max_attempts = max(self._max_retries, 5)
        for attempt in range(1, rate_limit_max_attempts + 1):
            try:
                response = client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                text = (response.text or "").strip()
                usage = None
                meta = getattr(response, "usage_metadata", None)
                if meta is not None:
                    usage = LLMUsage(
                        prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
                        completion_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
                        total_tokens=int(getattr(meta, "total_token_count", 0) or 0),
                    )
                return LLMResult(
                    text=text,
                    model=self._model,
                    provider=self.provider_name,
                    usage=usage,
                )
            except Exception as exc:
                last_exc = exc
                is_429 = _is_rate_limit_error(exc)
                max_attempts = rate_limit_max_attempts if is_429 else self._max_retries
                if attempt >= max_attempts:
                    break
                if is_429:
                    parsed = _extract_retry_delay_seconds(exc)
                    wait_s = min(max((parsed + 1.5) if parsed is not None else max(delay, 15.0), 1.0), 65.0)
                    logger.warning(
                        "Gemini generate rate-limited (429) on attempt %d/%d; waiting %.1fs...",
                        attempt,
                        max_attempts,
                        wait_s,
                    )
                    time.sleep(wait_s)
                    delay = max(delay * 2.0, wait_s)
                else:
                    logger.warning("Gemini generate attempt %d/%d failed: %s", attempt, max_attempts, exc)
                    time.sleep(delay)
                    delay *= 2.0

        raise RuntimeError(f"Gemini generation failed: {last_exc}") from last_exc

    def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Iterator[str]:
        client = self._get_client()
        contents, config = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
        )
        stream = client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )
        for chunk in stream:
            piece = getattr(chunk, "text", None)
            if piece:
                yield piece
