"""JustJoin.it integration using the public JSON API that powers justjoin.it.

Endpoints (verified 2026-10-07):
- ``GET /api/candidate-api/offers?categories=&experienceLevels=&keywords=&from=&itemsCount=`` - paginated listing
- ``GET /api/candidate-api/offers/<slug>`` - offer detail with HTML ``body``
- ``GET /api/candidate-api/offers/categories/count`` - category keys
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Self

import httpx

from job_seeker.config import JustJoinConfig
from job_seeker.domain.models import JobOffer
from job_seeker.sources.base import CategoryInfo, SourceError, SourceQuery
from job_seeker.sources.justjoin.mapper import SOURCE_NAME, map_offer

log = logging.getLogger(__name__)

BASE_URL = "https://justjoin.it/api/candidate-api"
USER_AGENT = "Mozilla/5.0 (compatible; job-seeker/0.1; personal job search assistant)"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class JustJoinSource:
    name = SOURCE_NAME

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        page_size: int = 100,
        request_delay_s: float = 0.5,
        max_retries: int = 3,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30.0,
        )
        self._page_size = page_size
        self._delay = request_delay_s
        self._max_retries = max_retries

    @classmethod
    def from_config(cls, config: JustJoinConfig) -> Self:
        return cls(page_size=config.page_size, request_delay_s=config.request_delay_s, max_retries=config.max_retries)

    async def fetch_offers(self, query: SourceQuery) -> AsyncIterator[JobOffer]:
        seen: set[str] = set()
        yielded = 0
        # One listing per category keeps every request small and lets a broken category fail alone.
        categories: list[str | None] = list(query.categories) or [None]
        for category in categories:
            offset = 0
            while True:
                params = self._listing_params(query, category, offset)
                page = await self._get_json("/offers", params)
                items: list[dict[str, Any]] = page.get("data") or []
                for raw in items:
                    try:
                        offer = map_offer(raw)
                    except Exception:  # one malformed offer must not abort the sync
                        log.warning("Skipping unparseable JustJoin offer %s", raw.get("slug"), exc_info=True)
                        continue
                    if offer.external_id in seen:
                        continue
                    seen.add(offer.external_id)
                    yield offer
                    yielded += 1
                    if query.limit is not None and yielded >= query.limit:
                        return
                total = (page.get("meta") or {}).get("totalItems", 0)
                offset += len(items)
                if not items or offset >= total:
                    break
                await asyncio.sleep(self._delay)

    async def fetch_details(self, offer: JobOffer) -> JobOffer:
        slug = offer.extra.get("slug")
        if not slug:
            return offer
        raw = await self._get_json(f"/offers/{slug}")
        detailed = map_offer(raw)
        return offer.model_copy(update={"description": detailed.description})

    async def list_categories(self) -> list[CategoryInfo]:
        data = await self._get_json("/offers/categories/count")
        if not isinstance(data, list):
            raise SourceError("Unexpected categories response from JustJoin.it")
        return sorted(
            (CategoryInfo(key=item["key"], count=item.get("count")) for item in data if item.get("key")),
            key=lambda c: c.key,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _listing_params(
        self, query: SourceQuery, category: str | None, offset: int
    ) -> list[tuple[str, str | int | float | bool | None]]:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("sortBy", "publishedAt"),
            ("orderBy", "descending"),
            ("from", str(offset)),
            ("itemsCount", str(self._page_size)),
        ]
        if category:
            params.append(("categories", category))
        params += [("experienceLevels", level.value) for level in query.experience_levels]
        if query.keywords:
            params.append(("keywords", query.keywords))
        return params

    async def _get_json(
        self, path: str, params: list[tuple[str, str | int | float | bool | None]] | None = None
    ) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise SourceError(f"JustJoin.it unreachable: {exc}") from exc
            else:
                if response.status_code not in RETRY_STATUSES:
                    if response.is_error:
                        raise SourceError(f"JustJoin.it returned HTTP {response.status_code} for {path}")
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise SourceError(f"JustJoin.it returned non-JSON response for {path}") from exc
                if attempt >= self._max_retries:
                    raise SourceError(f"JustJoin.it returned HTTP {response.status_code} for {path}")
            backoff = 2**attempt
            log.info("JustJoin request %s failed, retrying in %ss", path, backoff)
            await asyncio.sleep(backoff)
        raise AssertionError("unreachable")
