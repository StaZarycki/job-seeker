"""Experience relative to a specific offer.

Total years alone mislead when switching technologies: 3 years of Node.js make you "mid" for a Node.js
offer but closer to "junior" for a C++ one. For each offer we therefore estimate the candidate's
*effective* experience in the offer's main technologies:

    years(skill) = base + transfer_ratio * (total - base)

where ``base`` is the time the skill was used in CV positions (``profile.skill_years``), or
``declared_ratio * total`` for skills listed in the CV without a position, or 0 for unknown skills.
General engineering experience therefore always counts partially.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from job_seeker.config import ExperienceConfig
from job_seeker.domain.models import CandidateProfile, JobOffer, Seniority
from job_seeker.profile.cv_reader import seniority_for_years as level_for_years
from job_seeker.profile.skills import canonical_skill
from job_seeker.utils.text import contains_word

__all__ = ["OfferExperience", "allowed_levels", "level_for_years", "offer_experience", "years_for_skill"]

MAIN_SKILLS_COUNT = 3
DEFAULT_SKILL_LEVEL = 3
LEVEL_ORDER = [Seniority.INTERN, Seniority.JUNIOR, Seniority.MID, Seniority.SENIOR, Seniority.MANAGER]


@dataclass(frozen=True)
class OfferExperience:
    years: float
    level: Seniority
    main_skills: list[str]


def years_for_skill(skill: str, profile: CandidateProfile, config: ExperienceConfig) -> float:
    total = profile.years_of_experience
    canonical = canonical_skill(skill)
    if canonical in profile.skill_years:
        base = profile.skill_years[canonical]
    elif canonical in profile.skill_weights():
        base = config.declared_ratio * total
    else:
        base = 0.0
    base = min(base, total)
    return round(base + config.transfer_ratio * (total - base), 2)


def offer_experience(
    offer: JobOffer, profile: CandidateProfile, config: ExperienceConfig, target_skills: Sequence[str] = ()
) -> OfferExperience:
    """Effective experience for ``offer``: level-weighted average over its main required skills.

    Main skills are the required skills you are moving towards (``target_skills``) or that the job title
    names ("Senior C++ Developer"); if there are none, the highest-level required skills.
    """
    targets = {canonical_skill(t) for t in target_skills}
    main = [
        s for s in offer.required_skills if canonical_skill(s.name) in targets or contains_word(offer.title, s.name)
    ][:MAIN_SKILLS_COUNT]
    if not main:
        main = sorted(offer.required_skills, key=lambda s: -(s.level or DEFAULT_SKILL_LEVEL))[:MAIN_SKILLS_COUNT]
    if not main:
        years = profile.years_of_experience
    else:
        weights = [s.level or DEFAULT_SKILL_LEVEL for s in main]
        weighted = sum(w * years_for_skill(s.name, profile, config) for s, w in zip(main, weights, strict=True))
        years = round(weighted / sum(weights), 1)
    return OfferExperience(years=years, level=level_for_years(years), main_skills=[s.name for s in main])


def allowed_levels(level: Seniority) -> set[Seniority]:
    """Your level plus one step up (a realistic stretch). C-level counts as one step above manager."""
    if level is Seniority.C_LEVEL:
        return {Seniority.C_LEVEL}
    index = LEVEL_ORDER.index(level)
    allowed = set(LEVEL_ORDER[index : index + 2])
    if level is Seniority.MANAGER:
        allowed.add(Seniority.C_LEVEL)
    return allowed
