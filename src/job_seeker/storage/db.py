"""SQLite persistence: offers from all sources, cached AI assessments and sync history."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from job_seeker.domain.models import AIAssessment, AIResult, JobOffer

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id             TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    external_id    TEXT NOT NULL,
    category       TEXT,
    published_at   TEXT,
    expires_at     TEXT,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    data           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS offers_source_published ON offers (source, published_at);

CREATE TABLE IF NOT EXISTS ai_assessments (
    offer_id       TEXT NOT NULL,
    profile_hash   TEXT NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    data           TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (offer_id, profile_hash, provider, model)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    fetched        INTEGER NOT NULL DEFAULT 0,
    new_offers     INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);
"""


@dataclass(frozen=True)
class UpsertStats:
    fetched: int = 0
    new: int = 0


@dataclass(frozen=True)
class SyncRun:
    source: str
    started_at: datetime
    finished_at: datetime | None
    fetched: int
    new_offers: int
    error: str | None


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # A short-lived connection per unit of work keeps this safe across threads (FastAPI threadpool).
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- offers -------------------------------------------------------------------------------------

    def upsert_offers(self, offers: Iterable[JobOffer]) -> UpsertStats:
        now = _now()
        fetched = new = 0
        with self._connect() as conn:
            for offer in offers:
                fetched += 1
                row = conn.execute("SELECT data FROM offers WHERE id = ?", (offer.id,)).fetchone()
                if row is None:
                    new += 1
                elif offer.description is None:
                    # The listing has no description; keep one fetched earlier from the detail endpoint.
                    previous = JobOffer.model_validate_json(row["data"])
                    offer = offer.model_copy(update={"description": previous.description})
                conn.execute(
                    """
                    INSERT INTO offers (id, source, external_id, category, published_at, expires_at,
                                        first_seen_at, last_seen_at, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        category = excluded.category, published_at = excluded.published_at,
                        expires_at = excluded.expires_at, last_seen_at = excluded.last_seen_at,
                        data = excluded.data
                    """,
                    (
                        offer.id,
                        offer.source,
                        offer.external_id,
                        offer.category,
                        _iso(offer.published_at),
                        _iso(offer.expires_at),
                        now,
                        now,
                        offer.model_dump_json(),
                    ),
                )
        return UpsertStats(fetched=fetched, new=new)

    def list_offers(
        self,
        *,
        sources: list[str] | None = None,
        categories: list[str] | None = None,
        max_age_days: int | None = None,
        include_expired: bool = False,
    ) -> list[JobOffer]:
        clauses: list[str] = []
        params: list[str | None] = []
        if sources:
            clauses.append(f"source IN ({_placeholders(sources)})")
            params += sources
        if categories:
            clauses.append(f"category IN ({_placeholders(categories)})")
            params += categories
        if max_age_days is not None:
            clauses.append("published_at >= ?")
            params.append(_iso(datetime.now(UTC) - timedelta(days=max_age_days)))
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_now())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT data FROM offers {where} ORDER BY published_at DESC", params).fetchall()
        return [JobOffer.model_validate_json(r["data"]) for r in rows]

    def get_offer(self, offer_id: str) -> JobOffer | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM offers WHERE id = ?", (offer_id,)).fetchone()
        return JobOffer.model_validate_json(row["data"]) if row else None

    def save_offer(self, offer: JobOffer) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE offers SET data = ? WHERE id = ?", (offer.model_dump_json(), offer.id))

    def count_offers(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT source, COUNT(*) AS n FROM offers GROUP BY source").fetchall()
        return {r["source"]: r["n"] for r in rows}

    # --- AI assessment cache --------------------------------------------------------------------------

    def get_ai_result(self, offer_id: str, profile_hash: str, provider: str, model: str) -> AIResult | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT data, input_tokens, output_tokens FROM ai_assessments
                   WHERE offer_id = ? AND profile_hash = ? AND provider = ? AND model = ?""",
                (offer_id, profile_hash, provider, model),
            ).fetchone()
        if row is None:
            return None
        return AIResult(
            provider=provider,
            model=model,
            assessment=AIAssessment.model_validate_json(row["data"]),
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cached=True,
        )

    def save_ai_result(self, offer_id: str, profile_hash: str, result: AIResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ai_assessments
                   (offer_id, profile_hash, provider, model, data, input_tokens, output_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    offer_id,
                    profile_hash,
                    result.provider,
                    result.model,
                    result.assessment.model_dump_json(),
                    result.input_tokens,
                    result.output_tokens,
                    _now(),
                ),
            )

    # --- sync history ---------------------------------------------------------------------------------

    def start_sync(self, source: str) -> int:
        with self._connect() as conn:
            cur = conn.execute("INSERT INTO sync_runs (source, started_at) VALUES (?, ?)", (source, _now()))
            return int(cur.lastrowid or 0)

    def finish_sync(self, run_id: int, stats: UpsertStats, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at = ?, fetched = ?, new_offers = ?, error = ? WHERE id = ?",
                (_now(), stats.fetched, stats.new, error, run_id),
            )

    def last_syncs(self) -> list[SyncRun]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM sync_runs WHERE id IN (SELECT MAX(id) FROM sync_runs GROUP BY source)
                   ORDER BY source"""
            ).fetchall()
        return [
            SyncRun(
                source=r["source"],
                started_at=datetime.fromisoformat(r["started_at"]),
                finished_at=datetime.fromisoformat(r["finished_at"]) if r["finished_at"] else None,
                fetched=r["fetched"],
                new_offers=r["new_offers"],
                error=r["error"],
            )
            for r in rows
        ]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)
