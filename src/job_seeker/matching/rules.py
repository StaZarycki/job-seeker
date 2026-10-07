"""Deterministic offer scoring: hard filters plus a weighted 0-100 score with an explanation."""

from __future__ import annotations

from datetime import UTC, datetime

from job_seeker.config import ExperienceConfig, RuleWeights, SearchPreferences
from job_seeker.domain.models import CandidateProfile, JobOffer, RuleScore, Seniority, WorkplaceType
from job_seeker.matching.experience import OfferExperience, allowed_levels, offer_experience
from job_seeker.profile.skills import RELATED, RELATED_CREDIT, canonical_skill
from job_seeker.utils.text import contains_word, normalize_city

CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
# Typical years of experience expected for each level: (min, max).
EXPECTED_YEARS: dict[Seniority, tuple[float, float]] = {
    Seniority.INTERN: (0, 1),
    Seniority.JUNIOR: (0, 2),
    Seniority.MID: (2, 5),
    Seniority.SENIOR: (5, 50),
    Seniority.MANAGER: (6, 50),
    Seniority.C_LEVEL: (10, 50),
}
MATCHED_CREDIT_THRESHOLD = 0.5
# Bayesian smoothing of skill coverage: an offer listing a single matching skill is weaker evidence
# than one listing five, so coverage is pulled towards SKILL_PRIOR by SKILL_PRIOR_STRENGTH "virtual" skills.
SKILL_PRIOR = 0.5
SKILL_PRIOR_STRENGTH = 1.0
# Credit for a skill the candidate is moving towards (search.target_skills) but doesn't have yet.
TARGET_SKILL_CREDIT = 0.5


def rejection_reason(
    offer: JobOffer, prefs: SearchPreferences, experience: OfferExperience | None = None
) -> str | None:
    """Return why the offer is filtered out by the user's hard preferences, or None if it passes.

    With ``experience_levels = "auto"`` the allowed levels depend on the candidate's experience in this
    offer's technologies (``experience``): their level plus one step up.
    """
    if offer.seniority:
        if prefs.experience_levels == "auto":
            if experience is not None and offer.seniority not in allowed_levels(experience.level):
                return (
                    f"poziom {offer.seniority.value} - Twoje doświadczenie w {_skills_label(experience)} "
                    f"to ~{experience.years:g} lat ({experience.level.value})"
                )
        elif prefs.experience_levels and offer.seniority not in prefs.experience_levels:
            return f"poziom {offer.seniority.value} poza preferencjami"
    if offer.workplace_type and prefs.workplace and offer.workplace_type not in prefs.workplace:
        return f"tryb pracy {offer.workplace_type.value} poza preferencjami"
    if (
        prefs.onsite_only_in_preferred_cities
        and prefs.preferred_cities
        and offer.workplace_type in (WorkplaceType.HYBRID, WorkplaceType.OFFICE)
        and not _in_preferred_city(offer, prefs)
    ):
        return "praca stacjonarna/hybrydowa poza preferowanymi miastami"
    required = {canonical_skill(s.name) for s in offer.required_skills}
    for keyword in prefs.exclude_keywords:
        if contains_word(offer.title, keyword) or canonical_skill(keyword) in required:
            return f"wykluczone słowo kluczowe '{keyword}'"
    return None


def score_offer(
    offer: JobOffer,
    profile: CandidateProfile,
    prefs: SearchPreferences,
    weights: RuleWeights,
    now: datetime | None = None,
    experience: OfferExperience | None = None,
) -> RuleScore:
    """Score ``offer``; ``experience`` (see matching.experience) is computed with defaults if not given."""
    experience = experience or offer_experience(offer, profile, ExperienceConfig(), prefs.target_skills)
    notes: list[str] = []
    skills, matched, missing = _skills_component(offer, profile, prefs, notes)
    components = {
        "skills": skills,
        "title": _title_component(offer, profile, prefs, notes),
        "seniority": _seniority_component(offer, profile, experience, notes),
        "location": _location_component(offer, prefs, notes),
        "salary": _salary_component(offer, prefs, notes),
        "languages": _languages_component(offer, profile, notes),
        "freshness": _freshness_component(offer, now or datetime.now(UTC)),
    }
    weight_map = weights.model_dump()
    total_weight = sum(weight_map.values()) or 1.0
    score = sum(components[name] * weight_map[name] for name in components) / total_weight * 100
    return RuleScore(
        score=round(score, 1),
        breakdown={k: round(v, 3) for k, v in components.items()},
        matched_skills=matched,
        missing_skills=missing,
        notes=notes,
        effective_years=experience.years,
        effective_level=experience.level,
        main_skills=experience.main_skills,
    )


def _skills_component(
    offer: JobOffer, profile: CandidateProfile, prefs: SearchPreferences, notes: list[str]
) -> tuple[float, list[str], list[str]]:
    known = profile.skill_weights()
    for target in map(canonical_skill, prefs.target_skills):
        known[target] = max(known.get(target, 0.0), TARGET_SKILL_CREDIT)
    matched: list[str] = []
    missing: list[str] = []
    weighted_credit = total_importance = 0.0
    for skill in offer.required_skills:
        importance = 0.5 + (skill.level or 3) / 10  # level 1 -> 0.6 ... level 5 -> 1.0
        credit = _skill_credit(canonical_skill(skill.name), known)
        weighted_credit += importance * credit
        total_importance += importance
        (matched if credit >= MATCHED_CREDIT_THRESHOLD else missing).append(skill.name)

    if total_importance:
        coverage = (weighted_credit + SKILL_PRIOR * SKILL_PRIOR_STRENGTH) / (total_importance + SKILL_PRIOR_STRENGTH)
    else:
        coverage = SKILL_PRIOR * 0.8  # nothing to compare; the title component carries the signal
        notes.append("Oferta nie podaje wymaganych umiejętności")

    nice = offer.nice_to_have_skills
    nice_bonus = 0.0
    if nice:
        nice_hits = [s.name for s in nice if _skill_credit(canonical_skill(s.name), known) >= MATCHED_CREDIT_THRESHOLD]
        nice_bonus = 0.15 * len(nice_hits) / len(nice)
        matched += [f"{name} (mile widziane)" for name in nice_hits]
    return min(1.0, coverage + nice_bonus), matched, missing


def _title_component(offer: JobOffer, profile: CandidateProfile, prefs: SearchPreferences, notes: list[str]) -> float:
    """Does the job title look like the role the candidate wants (keywords or core skills in the title)?"""
    core_skills = [name for name, weight in profile.skill_weights().items() if weight >= 1.0]
    avoided = [k for k in prefs.avoid_title_keywords if contains_word(offer.title, k)]
    if avoided:
        notes.append(f"Tytuł zawiera niechciane: {', '.join(avoided)}")
        return 0.1
    if any(contains_word(offer.title, k) for k in [*prefs.title_keywords, *prefs.target_skills, *core_skills]):
        return 1.0
    return 0.4


def _skill_credit(skill: str, known: dict[str, float]) -> float:
    if skill in known:
        return known[skill]
    related = [known[r] * RELATED_CREDIT for r in RELATED.get(skill, ()) if r in known]
    return max(related, default=0.0)


def _seniority_component(
    offer: JobOffer, profile: CandidateProfile, experience: OfferExperience, notes: list[str]
) -> float:
    years = experience.years
    if years < profile.years_of_experience - 0.5:
        notes.append(
            f"Doświadczenie w technologiach oferty ({_skills_label(experience)}): "
            f"~{years:g} lat → {experience.level.value}"
        )
    if offer.seniority is None:
        return 0.7
    low, high = EXPECTED_YEARS[offer.seniority]
    if years < low:
        gap = low - years
        if gap >= 1:
            notes.append(f"Poziom {offer.seniority.value} zwykle wymaga ~{low:g}+ lat doświadczenia")
        return max(0.0, 1 - 0.25 * gap)
    if years > high:
        notes.append(f"Poziom {offer.seniority.value} może być poniżej Twoich kwalifikacji")
        return max(0.2, 1 - 0.3 * (years - high))
    return 1.0


def _location_component(offer: JobOffer, prefs: SearchPreferences, notes: list[str]) -> float:
    cities = ", ".join(dict.fromkeys(loc.city for loc in offer.locations)) or "?"
    match offer.workplace_type:
        case WorkplaceType.REMOTE:
            notes.append("Praca zdalna")
            return 1.0
        case WorkplaceType.HYBRID:
            notes.append(f"Hybrydowo: {cities}")
            return 0.9 if _in_preferred_city(offer, prefs) else 0.2
        case WorkplaceType.OFFICE:
            notes.append(f"Stacjonarnie: {cities}")
            return 0.75 if _in_preferred_city(offer, prefs) else 0.0
        case _:
            return 0.5


def _salary_component(offer: JobOffer, prefs: SearchPreferences, notes: list[str]) -> float:
    salary = offer.best_salary
    if salary is None:
        notes.append("Brak widełek")
        return 0.5
    low, high = salary.min_pln_month, salary.max_pln_month or salary.min_pln_month or 0
    notes.append(f"Widełki: {_pln(low)}–{_pln(high)} PLN/mies. ({salary.contract})")
    if prefs.min_salary_pln_month:
        if high >= prefs.min_salary_pln_month:
            return 1.0
        shortfall = (prefs.min_salary_pln_month - high) / prefs.min_salary_pln_month
        notes.append("Górne widełki poniżej Twojego minimum")
        return max(0.0, 1 - 2 * shortfall)
    return 0.5 + 0.5 * min(1.0, max(0.0, (high - 10_000) / 20_000))


def _languages_component(offer: JobOffer, profile: CandidateProfile, notes: list[str]) -> float:
    score = 1.0
    for req in offer.languages:
        have = profile.languages.get(req.code)
        need = req.level or "B1"
        if have is None:
            notes.append(f"Wymagany język {req.code.upper()} {need} - brak w profilu")
            score = min(score, 0.0)
        elif _cefr(have) < _cefr(need):
            notes.append(f"Wymagany {req.code.upper()} {need}, masz {have}")
            score = min(score, max(0.0, 1 - 0.35 * (_cefr(need) - _cefr(have))))
    return score


def _freshness_component(offer: JobOffer, now: datetime) -> float:
    if offer.published_at is None:
        return 0.5
    published = offer.published_at if offer.published_at.tzinfo else offer.published_at.replace(tzinfo=UTC)
    age_days = (now - published).total_seconds() / 86_400
    if age_days <= 3:
        return 1.0
    return max(0.3, 1 - 0.7 * (age_days - 3) / 27)


def _skills_label(experience: OfferExperience) -> str:
    return ", ".join(experience.main_skills) or "tej roli"


def _in_preferred_city(offer: JobOffer, prefs: SearchPreferences) -> bool:
    preferred = {normalize_city(c) for c in prefs.preferred_cities}
    return any(normalize_city(loc.city) in preferred for loc in offer.locations)


def _cefr(level: str) -> int:
    level = level.upper()
    return CEFR.index(level) if level in CEFR else 2


def _pln(value: float | None) -> str:
    return "?" if value is None else f"{value:,.0f}".replace(",", " ")
