from __future__ import annotations

from datetime import UTC, datetime, timedelta

from job_seeker.config import RuleWeights, SearchPreferences
from job_seeker.domain.models import (
    CandidateProfile,
    JobOffer,
    LanguageRequirement,
    Location,
    Salary,
    Seniority,
    Skill,
    WorkplaceType,
)
from job_seeker.matching.rules import rejection_reason, score_offer

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def make_offer(**kwargs: object) -> JobOffer:
    defaults: dict[str, object] = {
        "source": "test",
        "external_id": "1",
        "url": "https://example.com/1",
        "title": "Backend Developer",
        "company": "ACME",
        "seniority": Seniority.MID,
        "workplace_type": WorkplaceType.REMOTE,
        "locations": [Location(city="Warszawa")],
        "required_skills": [Skill(name="Node.js", level=4), Skill(name="TypeScript", level=4)],
        "published_at": NOW - timedelta(days=1),
    }
    return JobOffer.model_validate({**defaults, **kwargs})


def score(offer: JobOffer, profile: CandidateProfile, prefs: SearchPreferences | None = None) -> float:
    return score_offer(offer, profile, prefs or SearchPreferences(), RuleWeights(), NOW).score


def test_matching_backend_offer_scores_high(profile: CandidateProfile) -> None:
    result = score_offer(make_offer(), profile, SearchPreferences(), RuleWeights(), NOW)
    assert result.score >= 80
    assert result.matched_skills == ["Node.js", "TypeScript"]
    assert result.missing_skills == []


def test_different_stack_scores_lower(profile: CandidateProfile) -> None:
    java = make_offer(
        title="Java Developer", required_skills=[Skill(name="Java", level=5), Skill(name="Spring", level=4)]
    )
    assert score(java, profile) < score(make_offer(), profile) - 30


def test_related_skill_gives_partial_credit(profile: CandidateProfile) -> None:
    mysql = make_offer(required_skills=[Skill(name="MySQL", level=4)])
    oracle = make_offer(required_skills=[Skill(name="Oracle", level=4)])
    assert score(oracle, profile) < score(mysql, profile) < score(make_offer(), profile)


def test_seniority_fit(profile: CandidateProfile) -> None:
    mid = score(make_offer(seniority=Seniority.MID), profile)
    senior = score(make_offer(seniority=Seniority.SENIOR), profile)
    junior = score(make_offer(seniority=Seniority.JUNIOR), profile)
    c_level = score(make_offer(seniority=Seniority.C_LEVEL), profile)
    assert mid > senior > c_level
    assert mid > junior


def test_location_remote_beats_hybrid_elsewhere(profile: CandidateProfile) -> None:
    prefs = SearchPreferences(onsite_only_in_preferred_cities=False)
    remote = score(make_offer(), profile, prefs)
    hybrid_katowice = score(
        make_offer(workplace_type=WorkplaceType.HYBRID, locations=[Location(city="Katowice")]), profile, prefs
    )
    hybrid_gdansk = score(
        make_offer(workplace_type=WorkplaceType.HYBRID, locations=[Location(city="Gdańsk")]), profile, prefs
    )
    assert remote > hybrid_katowice > hybrid_gdansk


def test_city_matching_ignores_diacritics_and_english_names(profile: CandidateProfile) -> None:
    prefs = SearchPreferences(preferred_cities=["Kraków"])
    offer = make_offer(workplace_type=WorkplaceType.HYBRID, locations=[Location(city="Cracow")])
    assert rejection_reason(offer, prefs) is None


def test_salary_component(profile: CandidateProfile) -> None:
    prefs = SearchPreferences(min_salary_pln_month=20_000)
    rich = make_offer(salaries=[Salary(contract="b2b", min_pln_month=20_000, max_pln_month=28_000)])
    poor = make_offer(salaries=[Salary(contract="b2b", min_pln_month=8_000, max_pln_month=11_000)])
    unknown = make_offer(salaries=[Salary(contract="any")])
    assert score(rich, profile, prefs) > score(unknown, profile, prefs) > score(poor, profile, prefs)
    notes = score_offer(unknown, profile, prefs, RuleWeights(), NOW).notes
    assert "Brak widełek" in notes


def test_language_requirements(profile: CandidateProfile) -> None:
    english = make_offer(languages=[LanguageRequirement(code="en", level="B2")])
    german = make_offer(languages=[LanguageRequirement(code="de", level="B2")])
    assert score(english, profile) > score(german, profile)


def test_stale_offer_scores_lower(profile: CandidateProfile) -> None:
    fresh = score(make_offer(), profile)
    stale = score(make_offer(published_at=NOW - timedelta(days=40)), profile)
    assert fresh > stale


def test_offer_without_skills_uses_title(profile: CandidateProfile) -> None:
    titled = make_offer(title="Node.js Developer", required_skills=[])
    generic = make_offer(title="Software Engineer", required_skills=[])
    assert score(titled, profile) > score(generic, profile)


def test_hard_filters() -> None:
    prefs = SearchPreferences(
        experience_levels=[Seniority.MID, Seniority.SENIOR],
        workplace=[WorkplaceType.REMOTE, WorkplaceType.HYBRID],
        preferred_cities=["Katowice"],
        exclude_keywords=["Java", "PHP"],
    )
    assert rejection_reason(make_offer(), prefs) is None
    assert rejection_reason(make_offer(seniority=Seniority.JUNIOR), prefs)
    assert rejection_reason(make_offer(workplace_type=WorkplaceType.OFFICE), prefs)
    assert rejection_reason(make_offer(workplace_type=WorkplaceType.HYBRID, locations=[Location(city="Gdańsk")]), prefs)
    assert (
        rejection_reason(make_offer(workplace_type=WorkplaceType.HYBRID, locations=[Location(city="Katowice")]), prefs)
        is None
    )
    assert rejection_reason(make_offer(title="Senior Java Developer"), prefs)
    assert rejection_reason(make_offer(title="JavaScript Developer"), prefs) is None
    assert rejection_reason(make_offer(required_skills=[Skill(name="PHP", level=3)]), prefs)


def test_single_matching_skill_is_weaker_evidence_than_many(profile: CandidateProfile) -> None:
    one = make_offer(required_skills=[Skill(name="Python", level=4)])
    many = make_offer(
        required_skills=[Skill(name=n, level=4) for n in ("Python", "AWS", "PostgreSQL", "Docker", "REST")]
    )
    assert score(one, profile) < score(many, profile)


def test_title_keywords_and_avoided_words(profile: CandidateProfile) -> None:
    prefs = SearchPreferences(title_keywords=["backend"], avoid_title_keywords=["frontend"])
    backend = score(make_offer(title="Backend Engineer"), profile, prefs)
    neutral = score(make_offer(title="Software Engineer"), profile, prefs)
    frontend = score(make_offer(title="Frontend Engineer"), profile, prefs)
    assert backend > neutral > frontend


def test_target_skills_give_partial_credit_and_title_match(profile: CandidateProfile) -> None:
    cpp = make_offer(title="C++ Developer", required_skills=[Skill(name="C++", level=5), Skill(name="Linux", level=3)])
    without = score_offer(cpp, profile, SearchPreferences(), RuleWeights(), NOW)
    with_target = score_offer(cpp, profile, SearchPreferences(target_skills=["C++"]), RuleWeights(), NOW)
    assert with_target.score > without.score
    assert "C++" in with_target.matched_skills and "C++" in without.missing_skills
    assert with_target.breakdown["title"] == 1.0


def test_seniority_uses_effective_experience(profile: CandidateProfile) -> None:
    """4 years total but none in C++: a mid C++ role is a stretch, a junior one fits."""
    junior = make_offer(seniority=Seniority.JUNIOR, required_skills=[Skill(name="C++", level=5)])
    mid = make_offer(seniority=Seniority.MID, required_skills=[Skill(name="C++", level=5)])
    junior_score = score_offer(junior, profile, SearchPreferences(), RuleWeights(), NOW)
    mid_score = score_offer(mid, profile, SearchPreferences(), RuleWeights(), NOW)
    assert junior_score.breakdown["seniority"] > mid_score.breakdown["seniority"]
    assert junior_score.effective_level is Seniority.JUNIOR
    assert any("C++" in note for note in junior_score.notes)
