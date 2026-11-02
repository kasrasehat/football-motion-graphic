"""Merge API claims + web claims into build/match_dossier.json (claims C-xxx, facts by key, conflicts, coverage)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from tms import jsonio
from tms.research import facts as FX


def _priority(c: dict) -> tuple:
    """Higher is better: API > web tier 1 > tier 2 > tier 3, then more recent."""
    if c["origin"] == "api":
        rank = 4
    else:
        rank = 4 - min(s.get("tier", 3) for s in c["sources"])
    ts = max(s["retrieved_at"] for s in c["sources"])
    return (rank, c.get("as_of") or "", ts)


def _independent_domains(cs: list[dict]) -> set[str]:
    out = set()
    for c in cs:
        for s in c["sources"]:
            out.add("api" if s["kind"] == "api" else FX.domain(s["url"]))
    return out


def merge(project_id: str, brief: dict, api_claims: list[dict], web: dict | None, built_at: str, inputs: dict,
          api_calls: int) -> dict:
    claims = []
    n = 0
    for c in api_claims:
        n += 1
        claims.append({"id": f"C-{n:03d}", "origin": "api", "web_id": None, **{k: c[k] for k in
                       ("fact_key", "category", "statement", "value", "unit", "as_of", "sources", "confidence")}})
    single = {}
    for w in (web or {}).get("claims", []):
        n += 1
        claims.append({"id": f"C-{n:03d}", "origin": "web", "web_id": w["id"], **{k: w[k] for k in
                       ("fact_key", "category", "statement", "value", "unit", "as_of", "sources", "confidence")}})
        single[f"C-{n:03d}"] = bool(w.get("single_source"))
    by_key: dict[str, list[dict]] = {}
    for c in claims:
        if c["fact_key"]:
            by_key.setdefault(c["fact_key"], []).append(c)
    facts, conflicts = {}, []
    for key, cs in sorted(by_key.items()):
        cs_sorted = sorted(cs, key=_priority, reverse=True)
        best = cs_sorted[0]
        disagree = [c for c in cs_sorted[1:] if not FX.agree(key, best["value"], c["value"])]
        status = "agreed" if len(_independent_domains(cs)) >= 2 or best["origin"] == "api" else "single_source"
        if disagree:
            top_peer = [c for c in disagree if _priority(c)[0] == _priority(best)[0]]
            if top_peer:
                status = "conflict"
                conflicts.append({"fact_key": key, "claim_ids": [best["id"]] + [c["id"] for c in top_peer], "resolution": None})
            else:
                status = "resolved_conflict"
                why = "API data preferred" if best["origin"] == "api" else "higher-tier source preferred"
                conflicts.append({"fact_key": key, "claim_ids": [best["id"]] + [c["id"] for c in disagree], "resolution": why})
        facts[key] = {"value": best["value"], "unit": best["unit"], "claim_ids": [c["id"] for c in cs_sorted],
                      "status": status, "as_of": best["as_of"] or max(s["retrieved_at"] for s in best["sources"])}
    coverage: dict[str, int] = {}
    for c in claims:
        coverage[c["category"]] = coverage.get(c["category"], 0) + 1
    m = brief["match"]
    ko = facts.get("fixture.kickoff_utc", {}).get("value") or m["kickoff_utc"]
    return {
        "version": "1", "project_id": project_id, "inputs": inputs, "built_at": built_at,
        "data_mode": "api+web" if api_claims else "web",
        "fixture": {"home": m["home"], "away": m["away"], "competition": facts.get("fixture.competition", {}).get("value") or m["competition"],
                    "kickoff_utc": ko, "venue": facts.get("fixture.venue", {}).get("value") or m["venue"], "fixture_id": m["fixture_id"]},
        "claims": claims, "facts": facts, "conflicts": conflicts, "coverage": coverage, "api_calls": api_calls,
    }


# ---------------------------------------------------------------- query parsing for fixture resolution
WHEN = {"tonight": 0, "today": 0, "tomorrow": 1}


def parse_query(q: str, today: datetime) -> dict:
    """'Real Madrid vs Arsenal tonight' -> {home, away, date_from, date_to} (dates in YYYY-MM-DD)."""
    s = q.strip()
    when = None
    m = re.search(r"\b(tonight|today|tomorrow)\b|\b(\d{4}-\d{2}-\d{2})\b", s, re.I)
    if m:
        when = m.group(0).lower()
        s = (s[: m.start()] + s[m.end():]).strip(" ,.-")
    parts = re.split(r"\s+(?:vs\.?|v\.?|versus|against|-|x)\s+", s, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        raise ValueError("write the fixture as '<home> vs <away> [tonight|tomorrow|YYYY-MM-DD]'")
    home, away = (p.strip(" ,.") for p in parts)
    if when in WHEN:
        d0 = (today + timedelta(days=WHEN[when])).date()
        return {"home": home, "away": away, "date_from": str(d0), "date_to": str(d0 + timedelta(days=1))}
    if when:
        return {"home": home, "away": away, "date_from": when, "date_to": when}
    d0 = today.date()
    return {"home": home, "away": away, "date_from": str(d0), "date_to": str(d0 + timedelta(days=14))}


def now_iso() -> str:
    return jsonio.now_iso()
