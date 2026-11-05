"""Connects the standalone collector to this project: API-Football through tms's cached, budgeted client."""
from __future__ import annotations

from match_data_collector.contract import Fact, Gap, MatchQuery, Source
from tms.research import api_football as AF

PREFIX = {"H.": "home.", "A.": "away."}


def _key(fact_key: str) -> str:
    for old, new in PREFIX.items():
        if fact_key.startswith(old):
            return new + fact_key[len(old):]
    return fact_key


class ApiFootballAdapter:
    name = "api_football"

    def __init__(self, client: AF.Client):
        self.client = client

    def _fixture_id(self, q: MatchQuery) -> tuple[int | None, Gap | None]:
        if q.ids.get("api_football_fixture"):
            return int(q.ids["api_football_fixture"]), None
        if not q.date:
            return None, Gap(self.name, "fixture", "invalid_input", "needs a fixture id or a date")
        found = AF.resolve(self.client, q.home, q.away, q.date, q.date)
        if len(found) == 1:
            return int(found[0]["fixture_id"]), None
        return None, Gap(self.name, "fixture", "ambiguous" if found else "not_found", f"{len(found)} fixtures matched")

    def collect(self, query: MatchQuery, now_iso: str) -> tuple[list[Fact], list[Gap]]:
        if not self.client.available:
            return [], [Gap(self.name, "all", "unavailable", "no API key configured")]
        try:
            fid, gap = self._fixture_id(query)
            if gap:
                return [], [gap]
            claims, _ = AF.pull(self.client, fid, now_iso)
        except AF.QuotaExceeded as e:
            return [], [Gap(self.name, "all", "quota", str(e))]
        except AF.ApiError as e:
            text = str(e)
            return [], [Gap(self.name, "all", "plan_limited" if "plan" in text.lower() else "unavailable", text)]
        facts = []
        for c in claims:
            s = c["sources"][0]
            facts.append(Fact(key=_key(c["fact_key"]), value=c["value"], statement=c["statement"], unit=c.get("unit"), as_of=c.get("as_of"),
                              confidence=c.get("confidence", "high"),
                              source=Source(adapter=self.name, kind="api", retrieved_at=s["retrieved_at"], endpoint=s.get("endpoint"),
                                            field_path=s.get("field_path"), publisher="API-Football")))
        return facts, []
