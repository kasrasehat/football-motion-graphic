from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Source = Literal["soccerway", "ballhelper", "sofascore"]
CATEGORIES = (
    "summary",
    "statistics",
    "lineups",
    "incidents",
    "players",
    "recent_player_form",
    "team_analysis",
    "h2h",
    "standings",
    "odds",
    "news",
    "extra",
)


def now() -> datetime:
    return datetime.now(UTC)


class MatchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    opponent_a: str = Field(min_length=2, max_length=120)
    opponent_b: str = Field(min_length=2, max_length=120)
    date: date
    timezone: str = "UTC"
    aliases_a: list[str] = Field(default_factory=list, max_length=20)
    aliases_b: list[str] = Field(default_factory=list, max_length=20)
    sources: list[Source] = Field(
        default_factory=lambda: ["soccerway", "ballhelper", "sofascore"], min_length=1
    )
    seed_urls: dict[Source, list[str]] = Field(default_factory=dict)
    include_news: bool = True
    news_days: int = Field(default=7, ge=0, le=90)
    browser: bool = True
    max_pages_per_source: int = Field(default=30, ge=2, le=300)
    max_news: int = Field(default=15, ge=0, le=100)
    # Ballhelper publishes wall-clock dates without a machine-readable timezone.
    # Leave unknown unless the operator has established the site's convention.
    ballhelper_timezone: str | None = None

    @field_validator("timezone", "ballhelper_timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("Use an IANA timezone, such as UTC or Asia/Tehran") from exc
        return value

    @model_validator(mode="after")
    def distinct(self):
        if self.opponent_a.casefold() == self.opponent_b.casefold():
            raise ValueError("Opponents must be different")
        self.sources = list(dict.fromkeys(self.sources))
        if sum(map(len, self.seed_urls.values())) > 30:
            raise ValueError("At most 30 source URLs are allowed")
        return self


class Evidence(BaseModel):
    url: str
    fetched_at: datetime = Field(default_factory=now)
    status_code: int | None = None
    content_type: str = ""
    sha256: str | None = None
    artifact: str | None = None
    cached: bool = False
    error: str | None = None


class Candidate(BaseModel):
    source_id: str
    url: str
    home: str
    away: str
    kickoff: datetime | None = None
    source_date: date | None = None
    date_basis: str = "timestamp"
    competition: str | None = None
    confidence: float = 0
    date_verified: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class Coverage(BaseModel):
    status: Literal["collected", "not_discovered", "unavailable", "blocked", "disabled"] = "not_discovered"
    detail: str = "No corresponding data was discovered within the collection scope."


class SourceReport(BaseModel):
    source: Source
    status: Literal["partial", "not_found", "ambiguous", "unverified", "blocked", "error"] = "not_found"
    match: Candidate | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    data: dict[str, list[dict[str, Any]]] = Field(default_factory=lambda: {k: [] for k in CATEGORIES})
    coverage: dict[str, Coverage] = Field(default_factory=lambda: {k: Coverage() for k in CATEGORIES})
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)

    def add(self, category: str, data: dict, url: str, **metadata):
        self.data[category].append({"source_url": url, **metadata, "value": data})
        self.coverage[category] = Coverage(status="collected", detail="See source records and evidence.")


class CollectionReport(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    query: MatchQuery
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    status: str = "running"
    sources: list[SourceReport] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    scope: str = (
        "A bounded snapshot of discovered match pages, data responses, tabs and related news. "
        "Unknown fields and raw responses are retained. No guarantee of exhaustive website coverage."
    )
