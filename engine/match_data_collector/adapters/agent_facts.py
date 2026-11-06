"""Facts gathered by a research agent with its own web tools, in the contract's shape. Anything unsourced is rejected."""
from __future__ import annotations

import json
from pathlib import Path

from match_data_collector.contract import Fact, Gap, MatchQuery, Source


class AgentFactsAdapter:
    name = "agent_facts"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def collect(self, query: MatchQuery, now_iso: str) -> tuple[list[Fact], list[Gap]]:
        facts, gaps = [], []
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        for g in doc.get("gaps", []):
            gaps.append(Gap(self.name, str(g.get("need", "unknown")), g.get("reason", "not_found"), str(g.get("detail", ""))))
        for f in doc.get("facts", []):
            s = f.get("source") or {}
            if not (f.get("key") and f.get("statement") and s.get("url") and s.get("quote") and s.get("retrieved_at")):
                gaps.append(Gap(self.name, str(f.get("key", "unknown")), "invalid_input", "fact needs key, statement, source url, quote and retrieved_at"))
                continue
            src = Source(adapter=self.name, kind="agent", retrieved_at=s["retrieved_at"], url=s["url"], publisher=s.get("publisher"),
                         title=s.get("title"), tier=s.get("tier"), quote=s["quote"])
            facts.append(Fact(key=f["key"], value=f.get("value"), statement=f["statement"], source=src, unit=f.get("unit"),
                              as_of=f.get("as_of"), confidence=f.get("confidence", "medium")))
        return facts, gaps
