from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel


class LLMMessage(BaseModel):
    """Normalized chat message passed to any LLM provider."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMUsage(BaseModel):
    """Token accounting metadata returned by an LLM call when available."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResult(BaseModel):
    """Normalized completion payload returned by `LLMProvider.generate`."""

    text: str
    model: str
    provider: str
    usage: LLMUsage | None = None


class LLMProvider(ABC):
    """Pluggable interface for generative AI models (Gemini / OpenAI-compatible)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResult:
        raise NotImplementedError

    @abstractmethod
    def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Iterator[str]:
        raise NotImplementedError


class NullLLMProvider(LLMProvider):
    """Disabled provider used when `LLM_PROVIDER=none` or no credentials exist."""

    def __init__(self, *, provider_name: str = "none", model_name: str = "") -> None:
        self._provider_name = provider_name
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_configured(self) -> bool:
        return False

    def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResult:
        raise RuntimeError("LLM provider is not configured.")

    def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Iterator[str]:
        raise RuntimeError("LLM provider is not configured.")
        yield  # pragma: no cover
