"""Matching pipeline: hard filters -> rule score -> (mode ai) AI score of the top N -> ranking."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from job_seeker.config import AIConfig, ExperienceConfig, MatchingMode, RuleWeights, SearchPreferences
from job_seeker.domain.models import AIResult, AssessmentContext, CandidateProfile, JobOffer, MatchResult
from job_seeker.matching.ai.base import AIConfigurationError, AIScorer, AIScoringError
from job_seeker.matching.experience import offer_experience
from job_seeker.matching.rules import rejection_reason, score_offer
from job_seeker.profile.skills import canonical_skill
from job_seeker.storage.db import Database
from job_seeker.utils.text import fold

log = logging.getLogger(__name__)

OfferEnricher = Callable[[JobOffer], Awaitable[JobOffer]]
AIPlanCallback = Callable[[int, int], None]


@dataclass
class MatchReport:
    results: list[MatchResult]
    mode: MatchingMode
    considered: int = 0
    filtered_out: int = 0
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_calls: int = 0
    ai_cached: int = 0
    ai_failed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: list[str] = field(default_factory=list)


def rank_by_rules(
    offers: list[JobOffer],
    profile: CandidateProfile,
    prefs: SearchPreferences,
    weights: RuleWeights,
    now: datetime | None = None,
    experience_config: ExperienceConfig | None = None,
) -> tuple[list[MatchResult], int]:
    """Score every offer that passes the hard filters. Returns (results sorted best-first, filtered count)."""
    now = now or datetime.now(UTC)
    experience_config = experience_config or ExperienceConfig()
    best: dict[tuple[str, str], MatchResult] = {}
    filtered = 0
    for offer in offers:
        experience = offer_experience(offer, profile, experience_config, prefs.target_skills)
        if rejection_reason(offer, prefs, experience):
            filtered += 1
            continue
        rule = score_offer(offer, profile, prefs, weights, now, experience)
        result = MatchResult(offer=offer, rule=rule, final_score=rule.score)
        # Companies often post the same job several times (per city/category) - keep the best-scoring copy.
        key = (fold(offer.company), fold(offer.title))
        if key not in best or result.final_score > best[key].final_score:
            best[key] = result
    results = sorted(best.values(), key=lambda r: r.final_score, reverse=True)
    return results, filtered


async def run_matching(
    offers: list[JobOffer],
    profile: CandidateProfile,
    profile_hash: str,
    *,
    prefs: SearchPreferences,
    weights: RuleWeights,
    mode: MatchingMode,
    top: int,
    db: Database,
    ai_config: AIConfig,
    scorer: AIScorer | None = None,
    enrich: OfferEnricher | None = None,
    on_ai_plan: AIPlanCallback | None = None,
    experience_config: ExperienceConfig | None = None,
) -> MatchReport:
    experience_config = experience_config or ExperienceConfig()
    ranked, filtered = rank_by_rules(offers, profile, prefs, weights, experience_config=experience_config)
    report = MatchReport(results=ranked[:top], mode=mode, considered=len(offers), filtered_out=filtered)
    if mode is MatchingMode.BASIC or not ranked:
        return report
    if scorer is None:
        raise ValueError("AI mode requires a scorer")

    report.ai_provider, report.ai_model = scorer.provider, scorer.model
    # The AI sees the profile plus per-search context, so cached assessments are keyed by both.
    cache_key = assessment_key(profile_hash, prefs, experience_config)
    candidates = ranked[: ai_config.top_n]
    cached: dict[str, AIResult] = {}
    for result in candidates:
        hit = db.get_ai_result(result.offer.id, cache_key, scorer.provider, scorer.model)
        if hit is not None:
            cached[result.offer.id] = hit
    to_score = [r for r in candidates if r.offer.id not in cached]
    report.ai_cached = len(cached)
    if on_ai_plan:
        on_ai_plan(len(to_score), len(cached))

    semaphore = asyncio.Semaphore(ai_config.max_concurrency)

    async def assess(result: MatchResult) -> tuple[str, AIResult | None, str | None]:
        async with semaphore:
            offer = result.offer
            try:
                if enrich is not None and offer.description is None:
                    offer = await enrich(offer)
                    result.offer = offer
                context = AssessmentContext(
                    effective_years=result.rule.effective_years,
                    effective_level=result.rule.effective_level,
                    main_skills=result.rule.main_skills,
                    target_skills=prefs.target_skills,
                )
                ai = await scorer.assess(profile, offer, context)
            except AIConfigurationError:
                raise
            except AIScoringError as exc:
                return result.offer.id, None, str(exc)
            except Exception as exc:  # e.g. a source error while fetching the description
                log.warning("AI scoring of %s failed", result.offer.id, exc_info=True)
                return result.offer.id, None, f"{result.offer.id}: {exc}"
            db.save_ai_result(offer.id, cache_key, ai)
            return offer.id, ai, None

    # The first call runs alone so configuration problems (missing key, bad model) fail fast.
    outcomes = [await assess(to_score[0])] if to_score else []
    outcomes += await asyncio.gather(*(assess(r) for r in to_score[1:]))
    fresh: dict[str, AIResult] = {}
    for offer_id, ai, error in outcomes:
        if ai is not None:
            fresh[offer_id] = ai
            report.ai_calls += 1
            report.input_tokens += ai.input_tokens
            report.output_tokens += ai.output_tokens
        else:
            report.ai_failed += 1
            report.errors.append(error or offer_id)

    assessed: list[MatchResult] = []
    for result in candidates:
        ai = cached.get(result.offer.id) or fresh.get(result.offer.id)
        if ai is None:
            continue
        result.ai = ai
        result.final_score = round(
            ai_config.weight * ai.assessment.score + (1 - ai_config.weight) * result.rule.score, 1
        )
        assessed.append(result)
    assessed.sort(key=lambda r: r.final_score, reverse=True)
    # AI-assessed offers first, then the remaining rule-ranked ones.
    assessed_ids = {r.offer.id for r in assessed}
    report.results = (assessed + [r for r in ranked if r.offer.id not in assessed_ids])[:top]
    return report


def assessment_key(profile_hash: str, prefs: SearchPreferences, experience_config: ExperienceConfig) -> str:
    """Cache key for AI assessments: the profile plus everything search-specific the AI is told."""
    payload = json.dumps(
        {
            "profile": profile_hash,
            "targets": sorted(canonical_skill(s) for s in prefs.target_skills),
            "experience": experience_config.model_dump(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
