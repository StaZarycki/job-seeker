"""Claude scorer (default provider). Uses structured outputs so the answer always matches ``AIAssessment``."""

from __future__ import annotations

import os

import anthropic

from job_seeker.domain.models import AIAssessment, AIResult, AssessmentContext, CandidateProfile, JobOffer
from job_seeker.matching.ai.base import AIConfigurationError, AIScoringError
from job_seeker.matching.ai.prompt import build_offer_message, build_system_prompt

PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-haiku-4-5"
MAX_TOKENS = 16_000
MISSING_KEY_HELP = (
    "Brak klucza API Anthropic. Ustaw ANTHROPIC_API_KEY w pliku .env (zobacz .env.example) "
    "albo użyj trybu basic (--mode basic)."
)


class AnthropicScorer:
    provider = PROVIDER

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        api_key_env: str | None = None,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        if client is None:
            api_key = None
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if not api_key:
                    raise AIConfigurationError(f"Zmienna {api_key_env} (ai.api_key_env) jest pusta. {MISSING_KEY_HELP}")
            # Without an explicit key the SDK resolves ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / `ant` profiles.
            client = anthropic.AsyncAnthropic(api_key=api_key)
        self._client = client
        self._system_cache: tuple[int, list[anthropic.types.TextBlockParam]] | None = None

    async def assess(self, profile: CandidateProfile, offer: JobOffer, context: AssessmentContext) -> AIResult:
        try:
            response = await self._client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self._system(profile),
                messages=[{"role": "user", "content": build_offer_message(offer, context)}],
                output_format=AIAssessment,
            )
        except TypeError as exc:  # raised by the SDK when no credentials can be resolved
            if "authentication" in str(exc).lower():
                raise AIConfigurationError(MISSING_KEY_HELP) from exc
            raise
        except anthropic.AuthenticationError as exc:
            raise AIConfigurationError(f"Klucz API Anthropic został odrzucony. {MISSING_KEY_HELP}") from exc
        except anthropic.PermissionDeniedError as exc:
            raise AIConfigurationError(f"Klucz API nie ma dostępu do modelu {self.model}: {exc.message}") from exc
        except anthropic.NotFoundError as exc:
            raise AIConfigurationError(f"Nieznany model '{self.model}' (ai.model / --model).") from exc
        except anthropic.BadRequestError as exc:
            raise AIScoringError(f"Niepoprawne zapytanie dla oferty {offer.id}: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise AIScoringError("Przekroczony limit zapytań Anthropic (po ponowieniach SDK).") from exc
        except anthropic.APIStatusError as exc:
            raise AIScoringError(f"Błąd API Anthropic ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIScoringError(f"Brak połączenia z API Anthropic: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AIScoringError(f"Model odmówił oceny oferty {offer.id}.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise AIScoringError(f"Model nie zwrócił kompletnej oceny oferty {offer.id}.")
        return AIResult(
            provider=self.provider,
            model=self.model,
            assessment=response.parsed_output,
            input_tokens=response.usage.input_tokens
            + (response.usage.cache_read_input_tokens or 0)
            + (response.usage.cache_creation_input_tokens or 0),
            output_tokens=response.usage.output_tokens,
        )

    async def aclose(self) -> None:
        await self._client.close()

    def _system(self, profile: CandidateProfile) -> list[anthropic.types.TextBlockParam]:
        # The profile is identical for every offer in a run, so it is the cacheable prefix.
        # (Models have a minimum cacheable length; shorter prompts simply aren't cached.)
        key = hash(profile.model_dump_json())
        if self._system_cache is None or self._system_cache[0] != key:
            block: anthropic.types.TextBlockParam = {
                "type": "text",
                "text": build_system_prompt(profile),
                "cache_control": {"type": "ephemeral"},
            }
            self._system_cache = (key, [block])
        return self._system_cache[1]
