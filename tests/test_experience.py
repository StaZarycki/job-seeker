from __future__ import annotations

from datetime import date

import pytest

from job_seeker.config import ExperienceConfig, SearchPreferences
from job_seeker.domain.models import CandidateProfile, CandidateSkill, Seniority, Skill
from job_seeker.matching.ai.prompt import build_offer_message, build_system_prompt
from job_seeker.matching.experience import allowed_levels, offer_experience, years_for_skill
from job_seeker.matching.rules import rejection_reason
from job_seeker.profile import cv_reader
from job_seeker.profile.service import _skill_years
from tests.test_rules import make_offer

CONFIG = ExperienceConfig(transfer_ratio=0.35, declared_ratio=0.5)
CV_TEXT = """\
About me
Developer with 4 years of commercial experience.
Experience
Backend Developer, Gdansk
Initech 2022 - 2025
- Built microservices with NestJS, TypeScript and RabbitMQ on PostgreSQL.
Junior JavaScript Developer, Remote
Globex 2021 - 2022
- Expanded Jest test coverage.
Skills
Python, Docker
Education
Uni 2015 - 2020
"""


@pytest.fixture
def node_dev() -> CandidateProfile:
    """4 years total, 3 of them Node.js; Python only declared in Skills."""
    return CandidateProfile(
        years_of_experience=4,
        skills=[CandidateSkill(name=n) for n in ("node.js", "typescript", "javascript", "python")],
        skill_years={"node.js": 3, "typescript": 3, "javascript": 4},
    )


def test_experience_entries_split_positions() -> None:
    entries = cv_reader.experience_entries(CV_TEXT, today=date(2026, 7, 1))
    assert [(e.start, e.end) for e in entries] == [(2022, 2025), (2021, 2022)]
    assert entries[0].text.startswith("Backend Developer")
    assert "Jest" in entries[1].text and "NestJS" not in entries[1].text


def test_skill_years_follow_positions_and_implications() -> None:
    years = _skill_years(CV_TEXT, cap=4)
    assert years["nestjs"] == 3
    assert years["node.js"] == 3  # implied by NestJS
    assert years["javascript"] == 4  # 2021-2022 directly + 2022-2025 via Node.js, merged
    assert years["jest"] == 1
    assert "python" not in years  # only listed in Skills, not in a position
    assert "docker" not in years


def test_years_for_skill(node_dev: CandidateProfile) -> None:
    assert years_for_skill("Node.js", node_dev, CONFIG) == pytest.approx(3 + 0.35 * 1)
    assert years_for_skill("Python", node_dev, CONFIG) == pytest.approx(2 + 0.35 * 2)  # declared only
    assert years_for_skill("C++", node_dev, CONFIG) == pytest.approx(0.35 * 4)  # unknown: transfer only


def test_offer_experience_node_vs_cpp(node_dev: CandidateProfile) -> None:
    node = make_offer(required_skills=[Skill(name="Node.js", level=4), Skill(name="TypeScript", level=4)])
    cpp = make_offer(required_skills=[Skill(name="C++", level=5), Skill(name="Linux", level=3)])

    node_exp = offer_experience(node, node_dev, CONFIG)
    cpp_exp = offer_experience(cpp, node_dev, CONFIG)

    assert node_exp.years == pytest.approx(3.4, abs=0.05) and node_exp.level is Seniority.MID
    assert cpp_exp.years == pytest.approx(1.4, abs=0.05) and cpp_exp.level is Seniority.JUNIOR
    assert cpp_exp.main_skills == ["C++", "Linux"]


def test_offer_without_skills_uses_total_years(node_dev: CandidateProfile) -> None:
    assert offer_experience(make_offer(required_skills=[]), node_dev, CONFIG).years == 4


def test_allowed_levels() -> None:
    assert allowed_levels(Seniority.JUNIOR) == {Seniority.JUNIOR, Seniority.MID}
    assert allowed_levels(Seniority.MID) == {Seniority.MID, Seniority.SENIOR}
    assert allowed_levels(Seniority.SENIOR) == {Seniority.SENIOR, Seniority.MANAGER}


@pytest.mark.parametrize(
    ("skill", "level", "passes"),
    [
        ("C++", Seniority.JUNIOR, True),
        ("C++", Seniority.MID, True),
        ("C++", Seniority.SENIOR, False),
        ("Node.js", Seniority.JUNIOR, False),
        ("Node.js", Seniority.MID, True),
        ("Node.js", Seniority.SENIOR, True),
    ],
)
def test_auto_level_filter(node_dev: CandidateProfile, skill: str, level: Seniority, passes: bool) -> None:
    offer = make_offer(seniority=level, required_skills=[Skill(name=skill, level=5)])
    experience = offer_experience(offer, node_dev, CONFIG)
    reason = rejection_reason(offer, SearchPreferences(experience_levels="auto"), experience)
    assert (reason is None) is passes
    if not passes:
        assert reason is not None and skill in reason


def test_explicit_levels_still_work(node_dev: CandidateProfile) -> None:
    offer = make_offer(seniority=Seniority.JUNIOR, required_skills=[Skill(name="C++", level=5)])
    experience = offer_experience(offer, node_dev, CONFIG)
    assert rejection_reason(offer, SearchPreferences(experience_levels=[Seniority.MID]), experience)


def test_prompt_mentions_effective_experience(node_dev: CandidateProfile) -> None:
    from job_seeker.domain.models import AssessmentContext

    offer = make_offer(required_skills=[Skill(name="C++", level=5)])
    context = AssessmentContext(
        effective_years=1.4, effective_level=Seniority.JUNIOR, main_skills=["C++"], target_skills=["C++"]
    )
    message = build_offer_message(offer, context)
    assert "~1.4 years (level: junior)" in message
    assert "moving towards: C++" in message
    assert "node.js: 3" in build_system_prompt(node_dev)


def test_title_and_target_skills_define_main_skills(node_dev: CandidateProfile) -> None:
    """Equal-level skills: the technology named in the title/targets decides, not familiar side skills."""
    skills = [Skill(name=n, level=4) for n in ("Agile", "C++", "REST", "PostgreSQL")]
    by_title = offer_experience(make_offer(title="Senior C++ Developer", required_skills=skills), node_dev, CONFIG)
    by_target = offer_experience(
        make_offer(title="Software Engineer", required_skills=skills), node_dev, CONFIG, ["C++"]
    )
    for experience in (by_title, by_target):
        assert experience.main_skills == ["C++"]
        assert experience.level is Seniority.JUNIOR
