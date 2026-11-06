"""Turn a match_collector report into dossier claims. Only what it can prove becomes a fact; everything else is a gap.

Rules that keep this honest:
- a source counts only if it selected a date-verified match, oriented the same way round as the brief;
- only data from before kick-off is used, so a finished match can't leak its own result into its preview;
- no games means unknown, never zero, while a real zero stays zero; sample sizes travel with the numbers;
- published tables are checked to add up, because a parsing slip would otherwise reach the screen as a statistic.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from tms.research import facts as FX

PUBLISHER = {"soccerway": "Soccerway", "ballhelper": "ballhelper", "sofascore": "Sofascore"}
FORM_N = 5
MIN_SPLIT_GAMES = 5  # the goals model prefers venue splits, and one built on fewer games is noise
STANDING_RE = re.compile(r"^\s*(\d+)\.?\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+):(\d+)\s+(-?\d+)\s+(\d+)\b")
H2H_RE = re.compile(r"^([A-Z][a-z]{2} \d{1,2}, \d{4})\s+\S+\s+(.+?)\s+(\d+)\s+(\d+)\b")


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|cf|afc|sc|ac|utd|united|club)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def same_team(a: str, b: str) -> bool:
    x, y = _norm(a), _norm(b)
    return bool(x and y) and (x == y or x in y or y in x)


def _claim(s, path: str, url: str, key: str, category: str, statement: str, value, retrieved_at: str, run_id: str, unit=None) -> dict:
    return {"fact_key": key, "category": category, "statement": statement[:400], "value": value, "unit": unit, "as_of": retrieved_at,
            "confidence": "medium",
            "sources": [{"kind": "collector", "url": url, "publisher": PUBLISHER[s.source], "tier": FX.tier_of(s.match.url),
                         "field_path": f"sources[{s.source}].{path}", "run_id": run_id, "retrieved_at": retrieved_at}]}


def _orientation(s, brief: dict) -> str | None:
    """None if the source agrees with the brief on who is at home; otherwise why this source can't be used."""
    m = brief["match"]
    if same_team(s.match.home, m["home"]) and same_team(s.match.away, m["away"]):
        return None
    if same_team(s.match.home, m["away"]) and same_team(s.match.away, m["home"]):
        return f"source has {s.match.home} at home, the brief has {m['home']}: check the fixture"
    return f"source's fixture {s.match.home} v {s.match.away} is not the brief's {m['home']} v {m['away']}"


def _team_analysis(s, side: str, source_team: str, competition: str, kickoff: datetime, now: str, run: str, gaps: list) -> list[dict]:
    out = []
    for i, rec in enumerate(s.data.get("team_analysis", [])):
        if rec.get("relation") != "prior_competition_results":
            continue
        v = rec["value"]
        if datetime.fromisoformat(v["before_kickoff"]) > kickoff:
            gaps.append({"source": s.source, "need": f"{side}.results", "why": "sample runs past kick-off, so it was not used"})
            continue
        team = next((t for t in v.get("teams", []) if same_team(t["team"], source_team)), None)
        if not team:
            gaps.append({"source": s.source, "need": f"{side}.results", "why": f"{source_team} is not in the results sample"})
            continue
        base = f"data.team_analysis[{i}].value.teams[{v['teams'].index(team)}].splits"
        url = rec["source_url"]

        def add(path, key, category, statement, value, unit=None):
            out.append(_claim(s, f"{base}.{path}", url, f"{side}.{key}", category, statement, value, now, run, unit))
        for venue, sp in team["splits"].items():
            n = sp.get("played") or 0
            if not n:
                gaps.append({"source": s.source, "need": f"{side}.split.{venue}", "why": "no games in this split, so it is unknown"})
                continue
            add(venue, f"split.{venue}", "team_stats",
                f"{team['team']}, {venue}, {competition}: {n} games before this match.", {k: sp[k] for k in sp if k != "event_ids"})
            if venue == "overall":
                add("overall.goals_for", "goals_for_avg", "team_stats", f"{team['team']} in {competition}: {sp['goals_for']} goals in {n} games.",
                    round(sp["goals_for"] / n, 2), "goals/match")
                add("overall.goals_against", "goals_against_avg", "team_stats", f"{team['team']} in {competition}: {sp['goals_against']} conceded in {n} games.",
                    round(sp["goals_against"] / n, 2), "goals/match")
                form = list(reversed(sp.get("form_newest_first", [])[:FORM_N]))
                if form:
                    add("overall.form_newest_first", "form.last5", "form", f"{team['team']}'s last {len(form)} in {competition}, oldest first.", form)
            elif n >= MIN_SPLIT_GAMES:
                add(f"{venue}.goals_for", f"{venue}_goals_for_avg", "team_stats", f"{team['team']} {venue} in {competition}: {sp['goals_for']} goals in {n} games.",
                    round(sp["goals_for"] / n, 2), "goals/match")
                add(f"{venue}.goals_against", f"{venue}_goals_against_avg", "team_stats", f"{team['team']} {venue} in {competition}: {sp['goals_against']} conceded in {n} games.",
                    round(sp["goals_against"] / n, 2), "goals/match")
        break
    return out


def _standing(s, side: str, source_team: str, competition: str, now: str, run: str, gaps: list) -> list[dict]:
    hits = []
    for i, rec in enumerate(s.data.get("standings", [])):
        for j, row in enumerate(rec["value"].get("rows", [])):
            m = STANDING_RE.match(row.get("text", ""))
            if m and same_team(m.group(2), source_team):
                hits.append((i, j, rec["source_url"], m))
    if len(hits) != 1:
        if hits or s.data.get("standings"):
            gaps.append({"source": s.source, "need": f"{side}.standing", "why": f"{len(hits)} table rows matched {source_team}"})
        return []
    i, j, url, m = hits[0]
    pos, played, w, d, ld, pts = int(m.group(1)), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(10))
    if w + d + ld != played or pts != 3 * w + d:
        gaps.append({"source": s.source, "need": f"{side}.standing", "why": f"table row does not add up: {m.group(0)}"})
        return []
    path = f"data.standings[{i}].value.rows[{j}].text"
    return [_claim(s, path, url, f"{side}.standing.{k}", "standings", f"{m.group(2)} in {competition} table when collected: {k} {v}.", v, now, run)
            for k, v in (("position", pos), ("points", pts), ("played", played))]


def _h2h(s, home: str, away: str, kickoff: datetime, now: str, run: str) -> list[dict]:
    """Rows on this tab also list each team's other recent games: keep only meetings of these two, before this one."""
    out, url, used = [], None, None
    for i, rec in enumerate(s.data.get("h2h", [])):
        for row in rec["value"].get("rows", []):
            m = H2H_RE.match(row.get("text", ""))
            if not m:
                continue
            when = datetime.strptime(m.group(1), "%b %d, %Y").date()
            if when >= kickoff.date():
                continue
            teams = _norm(m.group(2))
            for first, second in ((home, away), (away, home)):
                if teams == _norm(first) + _norm(second):
                    out.append({"date": when.isoformat(), "home": first, "away": second, "score": f"{m.group(3)}-{m.group(4)}"})
                    url, used = rec["source_url"], i
    out = sorted(out, key=lambda r: r["date"], reverse=True)[:5]
    if not out:
        return []
    return [_claim(s, f"data.h2h[{used}].value.rows", url, "h2h.last5", "h2h", f"Last {len(out)} meetings of {home} and {away} shown by the source.", out, now, run)]


def map_report(report, brief: dict) -> dict:
    """Returns {"run_id", "claims", "gaps"}. A source that can't be used leaves gaps, and costs no other source its facts."""
    claims, gaps = [], []
    run = report.run_id
    collected = report.finished_at or report.started_at
    now = collected.isoformat().replace("+00:00", "Z")
    for s in report.sources:
        if not s.match or not s.match.date_verified:
            why = "; ".join(s.warnings[:2]) or "no date-verified match selected"
            gaps.append({"source": s.source, "need": "all", "why": f"{s.status}: {why}"[:300]})
            continue
        bad = _orientation(s, brief)
        if bad:
            gaps.append({"source": s.source, "need": "all", "why": bad})
            continue
        kickoff = s.match.kickoff
        comp, _, rnd = (s.match.competition or "").partition(" - ")
        url = s.match.url
        if kickoff:
            ko = kickoff.isoformat().replace("+00:00", "Z")
            claims.append(_claim(s, "match.kickoff", url, "fixture.kickoff_utc", "fixture", f"Kick-off {ko}.", ko, now, run))
        if comp:
            claims.append(_claim(s, "match.competition", url, "fixture.competition", "fixture", f"Competition: {comp}.", comp, now, run))
        if rnd:
            claims.append(_claim(s, "match.competition", url, "fixture.round", "fixture", f"Round: {rnd}.", rnd, now, run))
        for side, team in (("H", s.match.home), ("A", s.match.away)):
            if kickoff:
                claims += _team_analysis(s, side, team, comp or "this competition", kickoff, now, run, gaps)
            if kickoff and collected > kickoff:  # a table fetched after kick-off already counts this match
                gaps.append({"source": s.source, "need": f"{side}.standing", "why": "table was collected after kick-off, so it was not used"})
            else:
                claims += _standing(s, side, team, comp or "this competition", now, run, gaps)
        if kickoff:
            claims += _h2h(s, s.match.home, s.match.away, kickoff, now, run)
        for cat, cov in s.coverage.items():
            if cat in ("lineups", "odds", "news", "players") and cov.status != "collected":
                gaps.append({"source": s.source, "need": cat, "why": f"{cov.status}: {cov.detail}"[:300]})
    for c in claims:
        problem = FX.type_problem(c["fact_key"], c["value"])
        if problem:
            gaps.append({"source": c["sources"][0]["publisher"], "need": c["fact_key"], "why": problem})
    good = [c for c in claims if not FX.type_problem(c["fact_key"], c["value"])]
    return {"run_id": run, "claims": good, "gaps": gaps}
