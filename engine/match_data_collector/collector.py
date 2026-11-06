"""Runs adapters for one query. One adapter failing never loses another's facts, and every absence is reported."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from match_data_collector.contract import Fact, Gap, MatchQuery, Result
from match_data_collector.fetch import FetchRefused
from match_data_collector.policy import POLICIES


class Adapter(Protocol):
    name: str

    def collect(self, query: MatchQuery, now_iso: str) -> tuple[list[Fact], list[Gap]]: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Collector:
    def __init__(self, adapters: list[Adapter], now=utc_now):
        self.adapters, self.now = adapters, now

    def collect(self, query: MatchQuery) -> Result:
        now = self.now()
        res = Result(query=query, collected_at=now)
        ran = set()
        for a in self.adapters:
            ran.add(a.name)
            try:
                facts, gaps = a.collect(query, now)
            except FetchRefused as e:
                facts, gaps = [], [Gap(a.name, "all", e.reason, str(e))]
            except Exception as e:  # noqa: BLE001 - one source's bug must not cost the others their facts
                facts, gaps = [], [Gap(a.name, "all", "unavailable", f"{type(e).__name__}: {e}")]
            res.facts += facts
            res.gaps += gaps
            res.sources.append({"name": a.name, "status": "ran", "facts": len(facts), "gaps": len(gaps)})
        for p in POLICIES.values():
            if p.name not in ran and p.status != "allowed":
                res.gaps.append(Gap(p.name, "all", "not_permitted", p.reason))
                res.sources.append({"name": p.name, "status": "not_permitted", "facts": 0, "gaps": 1})
        return res
