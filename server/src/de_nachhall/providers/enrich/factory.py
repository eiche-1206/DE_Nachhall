"""按 LLM_PROVIDER 选实现。调用点不该知道有哪几家。"""

from __future__ import annotations

from de_nachhall.config import Settings
from de_nachhall.providers.enrich.base import EnrichProvider
from de_nachhall.providers.enrich.claude import ClaudeEnricher
from de_nachhall.providers.enrich.null import NullEnricher
from de_nachhall.providers.enrich.openai_compat import OpenAICompatEnricher


def build_enricher(settings: Settings) -> EnrichProvider:
    if settings.llm_provider == "claude":
        return ClaudeEnricher(
            api_key=settings.anthropic_api_key or "", model=settings.llm_model
        )
    if settings.llm_provider == "openai_compat":
        return OpenAICompatEnricher(
            api_key=settings.llm_api_key or "",
            base_url=settings.llm_base_url or "",
            model=settings.llm_model,
        )
    return NullEnricher()
