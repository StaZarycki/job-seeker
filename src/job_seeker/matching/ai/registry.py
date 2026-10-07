"""Pick an AI scorer implementation by provider name."""

from __future__ import annotations

from job_seeker.config import AIConfig
from job_seeker.matching.ai.base import AIConfigurationError, AIScorer

PROVIDERS = ("anthropic", "openai_compatible")


def create_scorer(config: AIConfig) -> AIScorer:
    if config.provider == "anthropic":
        from job_seeker.matching.ai.anthropic_scorer import AnthropicScorer

        return AnthropicScorer(config.model, api_key_env=config.api_key_env)
    if config.provider == "openai_compatible":
        from job_seeker.matching.ai.openai_compatible import OpenAICompatibleScorer

        return OpenAICompatibleScorer(config.model, base_url=config.base_url, api_key_env=config.api_key_env)
    raise AIConfigurationError(f"Nieznany dostawca AI '{config.provider}'. Dostępni: {', '.join(PROVIDERS)}")
