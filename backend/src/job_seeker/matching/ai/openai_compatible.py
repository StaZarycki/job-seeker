"""Scorer for any OpenAI-compatible chat API: OpenAI, OpenRouter, or local Ollama / LM Studio via ``base_url``.

Requires the optional dependency: ``uv sync --extra openai``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from job_seeker.domain.models import AIAssessment, AIResult, AssessmentContext, CandidateProfile, JobOffer
from job_seeker.matching.ai.base import AIConfigurationError, AIScoringError
from job_seeker.matching.ai.prompt import build_offer_message, build_system_prompt

if TYPE_CHECKING:
    from openai import AsyncOpenAI

PROVIDER = "openai_compatible"
DEFAULT_KEY_ENV = "OPENAI_API_KEY"


class OpenAICompatibleScorer:
    provider = PROVIDER

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        if client is None:
            try:
                import openai
            except ImportError as exc:
                raise AIConfigurationError(
                    "Dostawca openai_compatible wymaga pakietu openai: uruchom `uv sync --extra openai`."
                ) from exc
            key_env = api_key_env or DEFAULT_KEY_ENV
            api_key = os.environ.get(key_env)
            if not api_key:
                if base_url is None:
                    raise AIConfigurationError(f"Brak klucza API: ustaw {key_env} w pliku .env.")
                api_key = "not-needed"  # local servers (Ollama, LM Studio) ignore the key
            client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._client = client

    async def assess(self, profile: CandidateProfile, offer: JobOffer, context: AssessmentContext) -> AIResult:
        import openai

        messages: list[Any] = [
            {"role": "system", "content": build_system_prompt(profile)},
            {"role": "user", "content": build_offer_message(offer, context)},
        ]
        try:
            try:
                completion: Any = await self._client.chat.completions.parse(
                    model=self.model, messages=messages, response_format=AIAssessment
                )
                assessment = completion.choices[0].message.parsed
            except openai.BadRequestError:
                # Some compatible servers don't support json_schema; fall back to plain JSON mode.
                completion = await self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        *messages,
                        {
                            "role": "user",
                            "content": "Respond only with a JSON object matching this schema: "
                            + str(AIAssessment.model_json_schema()),
                        },
                    ],
                    response_format={"type": "json_object"},
                )
                assessment = AIAssessment.model_validate_json(completion.choices[0].message.content or "")
        except openai.AuthenticationError as exc:
            raise AIConfigurationError("Klucz API został odrzucony przez dostawcę.") from exc
        except openai.NotFoundError as exc:
            raise AIConfigurationError(f"Nieznany model '{self.model}' lub zły base_url.") from exc
        except openai.APIConnectionError as exc:
            raise AIConfigurationError(f"Brak połączenia z API ({exc}). Sprawdź ai.base_url.") from exc
        except openai.APIStatusError as exc:
            raise AIScoringError(f"Błąd API ({exc.status_code}): {exc.message}") from exc
        except ValidationError as exc:
            raise AIScoringError(f"Model zwrócił niepoprawny JSON dla oferty {offer.id}.") from exc

        if assessment is None:
            raise AIScoringError(f"Model nie zwrócił oceny oferty {offer.id}.")
        usage = completion.usage
        return AIResult(
            provider=self.provider,
            model=self.model,
            assessment=assessment,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    async def aclose(self) -> None:
        await self._client.close()
