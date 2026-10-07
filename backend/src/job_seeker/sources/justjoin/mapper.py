"""Translate JustJoin.it candidate-api JSON into domain ``JobOffer`` objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from job_seeker.domain.models import (
    JobOffer,
    LanguageRequirement,
    Location,
    Salary,
    Seniority,
    Skill,
    WorkplaceType,
)
from job_seeker.utils.text import html_to_text

SOURCE_NAME = "justjoin"
OFFER_URL = "https://justjoin.it/job-offer/{slug}"


def map_offer(raw: dict[str, Any]) -> JobOffer:
    """Map an item from the offers listing (or the detail endpoint, which uses ``id`` instead of ``guid``)."""
    slug = raw["slug"]
    external_id = raw.get("guid") or raw.get("id") or slug
    body = raw.get("body")
    return JobOffer(
        source=SOURCE_NAME,
        external_id=str(external_id),
        url=OFFER_URL.format(slug=slug),
        title=raw.get("title", "").strip(),
        company=(raw.get("companyName") or "").strip(),
        category=(raw.get("category") or {}).get("key"),
        seniority=_enum_or_none(Seniority, raw.get("experienceLevel")),
        workplace_type=_enum_or_none(WorkplaceType, raw.get("workplaceType")),
        working_time=raw.get("workingTime"),
        locations=_map_locations(raw),
        required_skills=_map_skills(raw.get("requiredSkills")),
        nice_to_have_skills=_map_skills(raw.get("niceToHaveSkills")),
        languages=[
            LanguageRequirement(code=lang["code"], level=lang.get("level"))
            for lang in raw.get("languages") or []
            if lang.get("code")
        ],
        salaries=map_salaries(raw.get("employmentTypes") or []),
        published_at=_parse_dt(raw.get("publishedAt")),
        expires_at=_parse_dt(raw.get("expiredAt")),
        apply_url=raw.get("applyUrl"),
        # The listing has a 200x200 thumbnail; the detail endpoint only the original image.
        company_logo_url=raw.get("companyLogoThumbUrl") or raw.get("companyLogoUrl"),
        description=html_to_text(body) if body else None,
        extra={"slug": slug},
    )


def map_salaries(employment_types: list[dict[str, Any]]) -> list[Salary]:
    """One ``Salary`` per contract type, in PLN.

    The API lists every contract type once per currency. ``from``/``to`` are already monthly amounts
    (hourly rates x168, daily x21, yearly /12); ``fromPerUnit``/``toPerUnit`` hold the original rate.
    """
    salaries = []
    for contract in dict.fromkeys(et.get("type") or "any" for et in employment_types):
        entries = [et for et in employment_types if (et.get("type") or "any") == contract]
        pln = next((et for et in entries if et.get("currency") == "PLN"), None)
        if pln is None:
            salaries.append(Salary(contract=contract))
            continue
        original = next((et for et in entries if et.get("currencySource") == "original"), pln)
        salaries.append(
            Salary(
                contract=contract,
                min_pln_month=_positive(pln.get("from")),
                max_pln_month=_positive(pln.get("to")) or _positive(pln.get("from")),
                gross=pln.get("gross"),
                original_currency=original.get("currency"),
                original_unit=(original.get("unit") or "").lower() or None,
                original_min=_positive(original.get("fromPerUnit")),
                original_max=_positive(original.get("toPerUnit")),
            )
        )
    return salaries


def _map_locations(raw: dict[str, Any]) -> list[Location]:
    locations = [
        Location(city=loc["city"], street=loc.get("street")) for loc in raw.get("locations") or [] if loc.get("city")
    ]
    if not locations and raw.get("city"):
        locations.append(Location(city=raw["city"], street=raw.get("street")))
    return locations


def _map_skills(items: list[dict[str, Any]] | None) -> list[Skill]:
    return [Skill(name=s["name"].strip(), level=s.get("level")) for s in items or [] if s.get("name")]


def _enum_or_none[E: (Seniority, WorkplaceType)](enum: type[E], value: Any) -> E | None:
    try:
        return enum(value)
    except ValueError:
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _positive(value: Any) -> float | None:
    if isinstance(value, int | float) and value > 0:
        return float(value)
    return None
