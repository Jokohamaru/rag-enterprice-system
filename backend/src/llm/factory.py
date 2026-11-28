from __future__ import annotations

from src.config.settings import Settings
from src.llm.base import LLMProvider, NullLLMProvider
from src.llm.gemini_provider import GeminiLLMProvider
from src.llm.openai_provider import OpenAICompatibleLLMProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Instantiate the configured LLM provider cleanly from application settings."""
    if settings.llm_provider == "none":
        return NullLLMProvider(provider_name="none", model_name="")

    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(
            api_key=settings.resolved_llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.resolved_llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    return GeminiLLMProvider(
        api_key=settings.resolved_llm_api_key,
        model=settings.resolved_llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
