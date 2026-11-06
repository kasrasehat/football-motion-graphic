"""The collector's data contract: one query in; sourced facts and explicit gaps out. Plain data, JSON-serialisable."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1"

# Why something is missing. Consumers can act on these without parsing messages.
GAP_REASONS = ("not_permitted", "blocked", "robots_disallowed", "not_covered", "not_found", "ambiguous", "parse_mismatch",
               "plan_limited", "quota", "unavailable", "invalid_input")


@dataclass(frozen=True)
class MatchQuery:
    home: str
    away: str
    date: str | None = None  # YYYY-MM-DD
    competition: str | None = None
    home_league: str | None = None  # domestic league of each team, for sources organised by league
    away_league: str | None = None
    ids: dict[str, str] = field(default_factory=dict)  # provider ids, e.g. {"api_football_fixture": "1635610"}


@dataclass(frozen=True)
class Source:
    adapter: str
    kind: str  # "web" | "api" | "agent"
    retrieved_at: str
    url: str | None = None
    endpoint: str | None = None
    field_path: str | None = None
    publisher: str | None = None
    title: str | None = None
    tier: int | None = None
    quote: str | None = None


@dataclass(frozen=True)
class Fact:
    key: str  # "fixture.venue", "home.league.points", ...
    value: Any
    statement: str
    source: Source
    unit: str | None = None
    as_of: str | None = None
    confidence: str = "medium"


@dataclass(frozen=True)
class Gap:
    adapter: str
    need: str
    reason: str
    detail: str = ""

    def __post_init__(self):
        if self.reason not in GAP_REASONS:
            raise ValueError(f"unknown gap reason {self.reason!r}")


@dataclass
class Result:
    query: MatchQuery
    collected_at: str
    facts: list[Fact] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)  # per source: name, status, adapter ran?, counts

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}
