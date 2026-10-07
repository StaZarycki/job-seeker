from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from job_seeker.config import AIConfig, MatchingMode, RuleWeights, SearchPreferences
from job_seeker.domain.models import AIAssessment, AssessmentContext, CandidateProfile, JobOffer, Seniority
from job_seeker.matching.ai.anthropic_scorer import DEFAULT_MODEL, AnthropicScorer
from job_seeker.matching.ai.base import AIConfigurationError, AIScoringError
from job_seeker.matching.ai.registry import create_scorer
from job_seeker.matching.pipeline import rank_by_rules, run_matching
from job_seeker.storage.db import Database
from tests.fakes import FakeScorer

CONTEXT = AssessmentContext(
    effective_years=1.4, effective_level=Seniority.JUNIOR, main_skills=["C++"], target_skills=["C++"]
)
PREFS = SearchPreferences(
    onsite_only_in_preferred_cities=False, experience_levels=[], workplace=[], max_offer_age_days=None
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


async def _run(
    offers: list[JobOffer], profile: CandidateProfile, db: Database, scorer: FakeScorer | None, **kwargs: Any
) -> Any:
    options: dict[str, Any] = {
        "prefs": PREFS,
        "weights": RuleWeights(),
        "mode": MatchingMode.AI if scorer else MatchingMode.BASIC,
        "top": 10,
        "db": db,
        "ai_config": AIConfig(top_n=3, weight=0.7),
        "scorer": scorer,
    }
    profile_hash = kwargs.pop("profile_hash", "hash-1")
    return await run_matching(offers, profile, profile_hash, **{**options, **kwargs})


def test_rank_by_rules_puts_node_offers_first(offers: list[JobOffer], profile: CandidateProfile) -> None:
    ranked, _ = rank_by_rules(offers, profile, PREFS, RuleWeights())
    top_titles = " ".join(r.offer.title.lower() for r in ranked[:3])
    assert "node" in top_titles or "backend" in top_titles or "full" in top_titles
    assert ranked == sorted(ranked, key=lambda r: r.final_score, reverse=True)


async def test_basic_mode_never_calls_ai(offers: list[JobOffer], profile: CandidateProfile, db: Database) -> None:
    report = await _run(offers, profile, db, None)
    assert report.mode is MatchingMode.BASIC
    assert all(r.ai is None for r in report.results)
    assert report.results[0].final_score == report.results[0].rule.score


async def test_ai_mode_scores_top_n_and_caches(offers: list[JobOffer], profile: CandidateProfile, db: Database) -> None:
    scorer = FakeScorer(score=100)
    planned: list[tuple[int, int]] = []
    report = await _run(offers, profile, db, scorer, on_ai_plan=lambda n, c: planned.append((n, c)))

    assert len(scorer.calls) == 3 and planned == [(3, 0)]
    assessed = [r for r in report.results if r.ai is not None]
    assert len(assessed) == 3
    assert report.results[:3] == assessed  # AI-assessed offers come first
    first = assessed[0]
    assert first.final_score == round(0.7 * 100 + 0.3 * first.rule.score, 1)
    assert report.input_tokens == 300

    second_scorer = FakeScorer(score=100)
    second = await _run(offers, profile, db, second_scorer)
    assert second_scorer.calls == []  # all from cache
    assert second.ai_cached == 3 and second.ai_calls == 0


async def test_profile_change_invalidates_ai_cache(
    offers: list[JobOffer], profile: CandidateProfile, db: Database
) -> None:
    await _run(offers, profile, db, FakeScorer())
    scorer = FakeScorer()
    await _run(offers, profile, db, scorer, profile_hash="hash-2")
    assert len(scorer.calls) == 3


async def test_model_change_gets_separate_cache(
    offers: list[JobOffer], profile: CandidateProfile, db: Database
) -> None:
    await _run(offers, profile, db, FakeScorer(model="a"))
    scorer = FakeScorer(model="b")
    await _run(offers, profile, db, scorer)
    assert len(scorer.calls) == 3


async def test_failed_offer_is_skipped(offers: list[JobOffer], profile: CandidateProfile, db: Database) -> None:
    ranked, _ = rank_by_rules(offers, profile, PREFS, RuleWeights())
    failing = ranked[1].offer.id
    report = await _run(offers, profile, db, FakeScorer(fail_ids={failing}))
    assert report.ai_failed == 1 and report.ai_calls == 2
    assert next(r for r in report.results if r.offer.id == failing).ai is None


async def test_configuration_error_aborts(offers: list[JobOffer], profile: CandidateProfile, db: Database) -> None:
    with pytest.raises(AIConfigurationError):
        await _run(offers, profile, db, FakeScorer(config_error=True))


async def test_offers_are_enriched_before_ai(offers: list[JobOffer], profile: CandidateProfile, db: Database) -> None:
    async def enrich(offer: JobOffer) -> JobOffer:
        return offer.model_copy(update={"description": "pełny opis"})

    scorer = FakeScorer()
    await _run(offers, profile, db, scorer, enrich=enrich)
    assert scorer.descriptions == ["pełny opis"] * 3


# --- Anthropic scorer -----------------------------------------------------------------------------


class _FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def _anthropic(messages: _FakeMessages) -> AnthropicScorer:
    client: Any = SimpleNamespace(messages=messages)
    return AnthropicScorer(client=client)


def _response(stop_reason: str = "end_turn", parsed: AIAssessment | None = None) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=50, output_tokens=40, cache_read_input_tokens=1000, cache_creation_input_tokens=0
    )
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed, usage=usage)


async def test_anthropic_scorer_request_shape(profile: CandidateProfile, offers: list[JobOffer]) -> None:
    assessment = AIAssessment(score=77, summary="ok", pros=[], cons=[], missing_skills=[])
    messages = _FakeMessages(_response(parsed=assessment))
    result = await _anthropic(messages).assess(profile, offers[0], CONTEXT)

    assert DEFAULT_MODEL == "claude-haiku-4-5"
    assert messages.kwargs["model"] == "claude-haiku-4-5"
    assert messages.kwargs["output_format"] is AIAssessment
    [system] = messages.kwargs["system"]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "Node.js" in system["text"]  # profile goes into the cached system prompt
    assert offers[0].title in messages.kwargs["messages"][0]["content"]
    assert result.assessment.score == 77
    assert result.input_tokens == 1050 and result.output_tokens == 40


async def test_anthropic_scorer_refusal(profile: CandidateProfile, offers: list[JobOffer]) -> None:
    with pytest.raises(AIScoringError):
        await _anthropic(_FakeMessages(_response(stop_reason="refusal"))).assess(profile, offers[0], CONTEXT)


async def test_anthropic_scorer_missing_credentials(profile: CandidateProfile, offers: list[JobOffer]) -> None:
    error = TypeError("Could not resolve authentication method. Expected one of api_key...")
    with pytest.raises(AIConfigurationError, match="ANTHROPIC_API_KEY"):
        await _anthropic(_FakeMessages(error=error)).assess(profile, offers[0], CONTEXT)


def test_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AIConfigurationError, match="Nieznany dostawca"):
        create_scorer(AIConfig(provider="nope"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AIConfigurationError, match="OPENAI_API_KEY"):
        create_scorer(AIConfig(provider="openai_compatible", model="gpt-x"))
    local = create_scorer(AIConfig(provider="openai_compatible", model="llama3", base_url="http://localhost:11434/v1"))
    assert local.provider == "openai_compatible" and local.model == "llama3"
    monkeypatch.delenv("MY_KEY", raising=False)
    with pytest.raises(AIConfigurationError, match="MY_KEY"):
        create_scorer(AIConfig(provider="anthropic", api_key_env="MY_KEY"))


def test_duplicate_postings_are_collapsed(offers: list[JobOffer], profile: CandidateProfile) -> None:
    copy = offers[0].model_copy(update={"external_id": "other-id"})
    ranked, _ = rank_by_rules([*offers, copy], profile, PREFS, RuleWeights())
    assert len(ranked) == len({(o.company, o.title) for o in offers})


async def test_anthropic_scorer_workspace_error_is_configuration_error(
    profile: CandidateProfile, offers: list[JobOffer]
) -> None:
    import anthropic
    import httpx2

    response = httpx2.Response(400, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    error = anthropic.BadRequestError(
        "This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header",
        response=response,
        body=None,
    )
    with pytest.raises(AIConfigurationError, match="ANTHROPIC_WORKSPACE_ID"):
        await _anthropic(_FakeMessages(error=error)).assess(profile, offers[0], CONTEXT)
