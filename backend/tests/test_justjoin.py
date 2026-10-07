from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from job_seeker.domain.models import Seniority, WorkplaceType
from job_seeker.sources.base import SourceError, SourceQuery
from job_seeker.sources.justjoin.client import BASE_URL, JustJoinSource
from job_seeker.sources.justjoin.mapper import map_offer, map_salaries


def test_maps_listing_offer(offers_page: dict[str, Any]) -> None:
    raw = next(o for o in offers_page["data"] if o["slug"].startswith("craftware-backend-engineer-node-js"))
    offer = map_offer(raw)

    assert offer.source == "justjoin"
    assert offer.external_id == raw["guid"]
    assert offer.id == f"justjoin:{raw['guid']}"
    assert offer.url == f"https://justjoin.it/job-offer/{raw['slug']}"
    assert offer.seniority in set(Seniority)
    assert offer.workplace_type in set(WorkplaceType)
    assert any(s.name.lower() in ("node.js", "nodejs") for s in offer.required_skills)
    assert offer.published_at is not None and offer.published_at.tzinfo is not None
    assert offer.description is None  # listing has no body
    assert offer.extra["slug"] == raw["slug"]


def test_every_fixture_offer_maps(offers_page: dict[str, Any]) -> None:
    offers = [map_offer(raw) for raw in offers_page["data"]]
    assert len(offers) == len(offers_page["data"])
    assert all(o.title and o.company and o.locations for o in offers)


def test_salary_uses_monthly_pln_and_keeps_original_rate() -> None:
    employment_types = [
        {"from": 25200.0, "fromPerUnit": 150.0, "to": 33600.0, "toPerUnit": 200.0, "currency": "PLN",
         "currencySource": "original", "type": "b2b", "unit": "Hour", "gross": False},
        {"from": 5900.0, "fromPerUnit": 35.0, "to": 7900.0, "toPerUnit": 47.0, "currency": "EUR",
         "currencySource": "conversion", "type": "b2b", "unit": "Hour", "gross": False},
    ]  # fmt: skip
    [salary] = map_salaries(employment_types)
    assert salary.contract == "b2b"
    assert (salary.min_pln_month, salary.max_pln_month) == (25200.0, 33600.0)
    assert salary.original_unit == "hour"
    assert (salary.original_min, salary.original_max) == (150.0, 200.0)


def test_salary_original_currency_is_not_pln() -> None:
    employment_types = [
        {"from": 10989.0, "fromPerUnit": 65.4, "to": 22625.0, "toPerUnit": 134.6, "currency": "PLN",
         "currencySource": "conversion", "type": "permanent", "unit": "Hour", "gross": True},
        {"from": 2856.0, "fromPerUnit": 17.0, "to": 5880.0, "toPerUnit": 35.0, "currency": "USD",
         "currencySource": "original", "type": "permanent", "unit": "Hour", "gross": True},
    ]  # fmt: skip
    [salary] = map_salaries(employment_types)
    assert salary.min_pln_month == 10989.0
    assert salary.original_currency == "USD"
    assert salary.original_min == 17.0
    assert salary.gross is True


def test_salary_without_range() -> None:
    employment_types = [
        {"from": None, "fromPerUnit": None, "to": None, "toPerUnit": None, "currency": "PLN",
         "currencySource": "original", "type": "any", "unit": "month", "gross": False},
    ]  # fmt: skip
    [salary] = map_salaries(employment_types)
    assert salary.min_pln_month is None and salary.max_pln_month is None


def test_detail_maps_description(offer_detail: dict[str, Any]) -> None:
    offer = map_offer(offer_detail)
    assert offer.external_id == offer_detail["id"]
    assert offer.description and "<p>" not in offer.description
    assert len(offer.description) > 200


@respx.mock
async def test_fetch_offers_paginates_and_deduplicates(offers_page: dict[str, Any]) -> None:
    items = offers_page["data"][:5]
    pages = {
        "0": {"data": items[:3], "meta": {"from": 0, "totalItems": 6}},
        "3": {"data": [*items[3:], items[0]], "meta": {"from": 3, "totalItems": 6}},  # items[0] repeated
    }
    route = respx.get(f"{BASE_URL}/offers").mock(
        side_effect=lambda request: httpx.Response(200, json=pages[request.url.params["from"]])
    )
    source = JustJoinSource(page_size=3, request_delay_s=0)

    offers = [o async for o in source.fetch_offers(SourceQuery(categories=["javascript"]))]
    await source.aclose()

    assert [o.external_id for o in offers] == [i["guid"] for i in items]
    assert route.call_count == 2
    params = route.calls[0].request.url.params
    assert params["categories"] == "javascript" and params["itemsCount"] == "3"


@respx.mock
async def test_fetch_offers_passes_server_side_filters() -> None:
    route = respx.get(f"{BASE_URL}/offers").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"totalItems": 0}})
    )
    source = JustJoinSource(request_delay_s=0)
    query = SourceQuery(categories=["python"], experience_levels=[Seniority.MID, Seniority.SENIOR], keywords="node")
    _ = [o async for o in source.fetch_offers(query)]
    await source.aclose()
    params = route.calls[0].request.url.params
    assert params.get_list("experienceLevels") == ["mid", "senior"]
    assert params["keywords"] == "node"


@respx.mock
async def test_retries_then_raises_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("job_seeker.sources.justjoin.client.asyncio.sleep", no_sleep)
    route = respx.get(f"{BASE_URL}/offers").mock(return_value=httpx.Response(503))
    source = JustJoinSource(max_retries=2, request_delay_s=0)
    with pytest.raises(SourceError, match="503"):
        _ = [o async for o in source.fetch_offers(SourceQuery(categories=["javascript"]))]
    await source.aclose()
    assert route.call_count == 3


@respx.mock
async def test_fetch_details(offers_page: dict[str, Any], offer_detail: dict[str, Any]) -> None:
    raw = next(o for o in offers_page["data"] if o["slug"] == offer_detail["slug"])
    respx.get(f"{BASE_URL}/offers/{raw['slug']}").mock(return_value=httpx.Response(200, json=offer_detail))
    source = JustJoinSource()
    offer = await source.fetch_details(map_offer(raw))
    await source.aclose()
    assert offer.external_id == raw["guid"]  # identity unchanged
    assert offer.description
