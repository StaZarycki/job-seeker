"""Prompt shared by every AI provider, so scores from different models are comparable."""

from __future__ import annotations

from job_seeker.domain.models import AssessmentContext, CandidateProfile, JobOffer, Skill

MAX_DESCRIPTION_CHARS = 12_000

SYSTEM_TEMPLATE = """\
You assess how well a job offer fits a specific candidate. You are helping the candidate decide \
which offers are worth applying to, so be honest and concrete rather than encouraging.

Score from 0 to 100:
- 85-100: strong fit - the candidate meets nearly all requirements and the role matches their direction
- 65-84: good fit - minor gaps that are easy to bridge
- 40-64: partial fit - noticeable gaps in core requirements, seniority or domain
- 0-39: poor fit - different stack, much higher seniority, or hard requirements the candidate lacks

Judge the core technical requirements first, then seniority and responsibilities, then location and \
language requirements. Treat closely related technologies (e.g. PostgreSQL vs MySQL) as partial matches. \
Base your answer only on the candidate profile and the offer; do not invent facts about either.

Judge seniority against the candidate's experience in the offer's main technologies (given with each \
offer), not against total years: 3 years of Node.js do not make someone a mid-level C++ developer, \
although general engineering experience partly transfers. When the candidate lists target skills they \
are moving towards, junior or entry-level roles in those technologies are legitimate goals - score them \
on how realistic and worthwhile the switch is, and value transferable experience.

Write summary, pros and cons in Polish. Keep each pro/con to one short sentence; give at most 4 of each. \
List in missing_skills only concrete skills the offer requires that the candidate does not show.

<candidate_profile>
{profile}
</candidate_profile>"""


def build_system_prompt(profile: CandidateProfile) -> str:
    skills = ", ".join(f"{s.name} ({s.weight:.2f})" for s in profile.skills)
    languages = ", ".join(f"{code}: {level}" for code, level in sorted(profile.languages.items()))
    skill_years = ", ".join(f"{name}: {years:g}" for name, years in profile.skill_years.items())
    body = "\n".join(
        [
            f"Headline: {profile.headline or '-'}",
            f"Location: {profile.location or '-'}",
            f"Years of commercial experience: {profile.years_of_experience:g} (level: {profile.seniority.value})",
            f"Skills (weight 1.0 = core, lower = secondary): {skills or '-'}",
            f"Years per skill, from positions in the CV: {skill_years or '-'}",
            f"Spoken languages: {languages or '-'}",
            "",
            "CV (contact details removed):",
            profile.cv_text,
        ]
    )
    return SYSTEM_TEMPLATE.format(profile=body)


def build_offer_message(offer: JobOffer, context: AssessmentContext | None = None) -> str:
    def skills(items: list[Skill]) -> str:
        return ", ".join(f"{s.name}" + (f" (level {s.level}/5)" if s.level else "") for s in items) or "-"

    salary = offer.best_salary
    salary_text = (
        f"{salary.min_pln_month or '?'}-{salary.max_pln_month or '?'} PLN/month ({salary.contract})" if salary else "-"
    )
    description = (offer.description or "(no description available)")[:MAX_DESCRIPTION_CHARS]
    lines = [
        "<job_offer>",
        f"Title: {offer.title}",
        f"Company: {offer.company}",
        f"Level: {offer.seniority.value if offer.seniority else '-'}",
        f"Workplace: {offer.workplace_type.value if offer.workplace_type else '-'}; "
        f"locations: {', '.join(loc.city for loc in offer.locations) or '-'}",
        f"Required skills: {skills(offer.required_skills)}",
        f"Nice to have: {skills(offer.nice_to_have_skills)}",
        f"Languages: {', '.join(f'{lang.code} {lang.level or ""}'.strip() for lang in offer.languages) or '-'}",
        f"Salary: {salary_text}",
        "",
        "Description:",
        description,
        "</job_offer>",
    ]
    if context is not None and context.effective_years is not None:
        level = f" (level: {context.effective_level.value})" if context.effective_level else ""
        lines.append(
            f"Candidate's effective experience in this offer's main technologies "
            f"({', '.join(context.main_skills) or 'the role'}): ~{context.effective_years:g} years{level}."
        )
    if context is not None and context.target_skills:
        lines.append(f"The candidate is moving towards: {', '.join(context.target_skills)}.")
    lines += ["", "Assess how well this offer fits the candidate."]
    return "\n".join(lines)
