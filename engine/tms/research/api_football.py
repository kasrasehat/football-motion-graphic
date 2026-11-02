"""API-Football v3 client (https://v3.football.api-sports.io, header x-apisports-key) and claim extraction.

Response shapes follow the public v3 documentation ({"get","parameters","errors","results","paging","response"}).
Live verification is pending (no key yet; this machine may be geo-blocked — opt-in proxy via TMS_HTTPS_PROXY).
Every request is cached with an endpoint-specific TTL; cache hits do not count against the quota.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from tms import envfile, jsonio, paths

BASE = "https://v3.football.api-sports.io"
TTL_S = {"/teams": 30 * 86400, "/coachs": 7 * 86400, "/standings": 12 * 3600, "/teams/statistics": 12 * 3600,
         "/fixtures/headtohead": 24 * 3600, "/fixtures": 1800, "/injuries": 1800, "/fixtures/lineups": 600, "/odds": 1800,
         "/status": 0}


class ApiError(Exception):
    pass


class QuotaExceeded(ApiError):
    pass


class Client:
    def __init__(self, key: str | None = None, cache_dir=None, max_calls: int | None = None, usage_file=None, now=None):
        self.key = key if key is not None else envfile.get("API_FOOTBALL_KEY").strip()
        self.cache = cache_dir or paths.scratch_dir() / "cache" / "api-football"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.usage_file = usage_file
        self.calls = 0
        self.now = now or (lambda: time.time())

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _used(self) -> int:
        if self.usage_file and self.usage_file.is_file():
            return int(jsonio.read_json(self.usage_file).get("calls", 0))
        return self.calls

    def _count(self) -> None:
        self.calls += 1
        if self.usage_file:
            used = self._used() + 1 if self.usage_file.is_file() else 1
            jsonio.write_json(self.usage_file, {"calls": used})

    def get(self, path: str, **params) -> dict:
        h = jsonio.sha256_bytes(jsonio.canonical({"path": path, "params": params}))
        f = self.cache / f"{path.strip('/').replace('/', '_')}-{h[:24]}.json"
        ttl = TTL_S.get(path, 1800)
        if f.is_file() and self.now() - f.stat().st_mtime < ttl:
            return jsonio.read_json(f)
        if not self.key:
            raise ApiError("API_FOOTBALL_KEY is not set — research runs web-only")
        if self.max_calls is not None and self._used() >= self.max_calls:
            raise QuotaExceeded(f"project API budget of {self.max_calls} calls reached")
        proxy = envfile.get("TMS_HTTPS_PROXY").strip() or None
        try:
            r = httpx.get(BASE + path, params=params, headers={"x-apisports-key": self.key}, timeout=60, proxy=proxy)
        except httpx.HTTPError as e:
            raise ApiError(f"network error calling API-Football {path}: {type(e).__name__}") from e
        self._count()
        if r.status_code >= 400:
            raise ApiError(f"API-Football {path} -> HTTP {r.status_code}")
        d = r.json()
        errs = d.get("errors")
        if errs and (isinstance(errs, dict) and errs or isinstance(errs, list) and errs):
            text = str(errs)
            if "limit" in text.lower() or "requests" in text.lower():
                raise QuotaExceeded(f"API-Football quota: {text[:200]}")
            raise ApiError(f"API-Football {path} error: {text[:300]}")
        if r.headers.get("x-ratelimit-requests-remaining") == "0":
            d["_quota_exhausted"] = True
        jsonio.write_json(f, d, compact=True)
        return d


# ---------------------------------------------------------------- claim extraction
def _claim(key, category, statement, value, endpoint, field_path, retrieved_at, unit=None, as_of=None):
    return {"fact_key": key, "category": category, "statement": statement, "value": value, "unit": unit,
            "as_of": as_of, "sources": [{"kind": "api", "endpoint": endpoint, "field_path": field_path, "retrieved_at": retrieved_at}],
            "confidence": "high", "origin": "api"}


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _result(goals_for, goals_against) -> str:
    return "W" if goals_for > goals_against else ("D" if goals_for == goals_against else "L")


def pull(client: Client, fixture_id: int, now_iso: str) -> tuple[list[dict], dict]:
    """Fetch the standard bundle for one fixture and return (claims, raw responses)."""
    raw, claims = {}, []
    fx = client.get("/fixtures", id=fixture_id)
    raw["fixture"] = fx
    if not fx.get("response"):
        raise ApiError(f"fixture {fixture_id} not found")
    f0 = fx["response"][0]
    home, away = f0["teams"]["home"], f0["teams"]["away"]
    league, season = f0["league"]["id"], f0["league"]["season"]
    ids = {"H": home["id"], "A": away["id"]}
    names = {"H": home["name"], "A": away["name"]}
    ko = datetime.fromisoformat(f0["fixture"]["date"]).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    claims.append(_claim("fixture.kickoff_utc", "fixture", f"Kick-off {ko}", ko, "/fixtures", "response[0].fixture.date", now_iso))
    venue = (f0["fixture"].get("venue") or {}).get("name")
    if venue:
        claims.append(_claim("fixture.venue", "fixture", f"Venue {venue}", venue, "/fixtures", "response[0].fixture.venue.name", now_iso))
    claims.append(_claim("fixture.competition", "fixture", f0["league"]["name"], f0["league"]["name"], "/fixtures", "response[0].league.name", now_iso))
    if f0["league"].get("round"):
        claims.append(_claim("fixture.round", "fixture", f0["league"]["round"], f0["league"]["round"], "/fixtures", "response[0].league.round", now_iso))
    if f0["fixture"].get("referee"):
        claims.append(_claim("fixture.referee", "fixture", f0["fixture"]["referee"], f0["fixture"]["referee"], "/fixtures", "response[0].fixture.referee", now_iso))
    for t in "HA":
        last = client.get("/fixtures", team=ids[t], last=5)
        raw[f"last5_{t}"] = last
        form = []
        for g in sorted(last.get("response", []), key=lambda r: r["fixture"]["date"]):
            is_home = g["teams"]["home"]["id"] == ids[t]
            gf, ga = (g["goals"]["home"], g["goals"]["away"]) if is_home else (g["goals"]["away"], g["goals"]["home"])
            if gf is not None and ga is not None:
                form.append(_result(gf, ga))
        if form:
            claims.append(_claim(f"{t}.form.last5", "form", f"{names[t]} last {len(form)}: {''.join(form)}", form,
                                 "/fixtures", f"response[*] (team={ids[t]}, last=5)", now_iso))
        st = client.get("/teams/statistics", league=league, season=season, team=ids[t])
        raw[f"stats_{t}"] = st
        r = st.get("response") or {}
        g = r.get("goals") or {}
        for key, path_ in (("goals_for_avg", ("for", "total")), ("goals_against_avg", ("against", "total")),
                           ("home_goals_for_avg", ("for", "home")), ("home_goals_against_avg", ("against", "home")),
                           ("away_goals_for_avg", ("for", "away")), ("away_goals_against_avg", ("against", "away"))):
            v = _num(((g.get(path_[0]) or {}).get("average") or {}).get(path_[1]))
            if v is not None:
                claims.append(_claim(f"{t}.{key}", "team_stats", f"{names[t]} {key.replace('_', ' ')} {v}", v, "/teams/statistics",
                                     f"response.goals.{path_[0]}.average.{path_[1]}", now_iso, unit="goals/match", as_of=now_iso))
        cs = ((r.get("clean_sheet") or {}).get("total"))
        if isinstance(cs, int):
            claims.append(_claim(f"{t}.clean_sheets", "team_stats", f"{names[t]} clean sheets {cs}", cs, "/teams/statistics",
                                 "response.clean_sheet.total", now_iso))
        lineups = r.get("lineups") or []
        if lineups:
            top = max(lineups, key=lambda x: x.get("played", 0))
            claims.append(_claim(f"{t}.formation", "tactics", f"{names[t]} most used formation {top['formation']}", top["formation"],
                                 "/teams/statistics", "response.lineups[max played].formation", now_iso))
        co = client.get("/coachs", team=ids[t])
        raw[f"coach_{t}"] = co
        if co.get("response"):
            name = co["response"][0]["name"]
            claims.append(_claim(f"{t}.manager", "tactics", f"{names[t]} manager {name}", name, "/coachs", "response[0].name", now_iso))
    stand = client.get("/standings", league=league, season=season)
    raw["standings"] = stand
    for grp in ((stand.get("response") or [{}])[0].get("league", {}).get("standings") or []):
        for row in grp:
            for t in "HA":
                if row["team"]["id"] == ids[t]:
                    claims.append(_claim(f"{t}.standing.position", "standings", f"{names[t]} {row['rank']}", row["rank"], "/standings",
                                         "response[0].league.standings[][].rank", now_iso))
                    claims.append(_claim(f"{t}.standing.points", "standings", f"{names[t]} {row['points']} pts", row["points"],
                                         "/standings", "response[0].league.standings[][].points", now_iso))
                    claims.append(_claim(f"{t}.standing.played", "standings", f"{names[t]} played {row['all']['played']}",
                                         row["all"]["played"], "/standings", "response[0].league.standings[][].all.played", now_iso))
    h2h = client.get("/fixtures/headtohead", h2h=f"{ids['H']}-{ids['A']}", last=5)
    raw["h2h"] = h2h
    res = [{"date": g["fixture"]["date"][:10], "home": g["teams"]["home"]["name"], "away": g["teams"]["away"]["name"],
            "score": f"{g['goals']['home']}-{g['goals']['away']}"} for g in sorted(h2h.get("response", []), key=lambda r: r["fixture"]["date"], reverse=True)
           if g["goals"]["home"] is not None]
    if res:
        claims.append(_claim("h2h.last5", "h2h", f"last {len(res)} meetings", res, "/fixtures/headtohead", "response[*]", now_iso))
    inj = client.get("/injuries", fixture=fixture_id)
    raw["injuries"] = inj
    for t in "HA":
        lst = [{"player": i["player"]["name"], "reason": i["player"].get("reason") or "",
                "status": "doubt" if (i["player"].get("type") or "").lower().startswith("question") else "out"}
               for i in inj.get("response", []) if i["team"]["id"] == ids[t]]
        claims.append(_claim(f"{t}.injuries", "injury", f"{names[t]}: {len(lst)} absences", lst, "/injuries",
                             f"response[team.id={ids[t]}]", now_iso, as_of=now_iso))
    lu = client.get("/fixtures/lineups", fixture=fixture_id)
    raw["lineups"] = lu
    for row in lu.get("response", []):
        t = "H" if row["team"]["id"] == ids["H"] else "A"
        xi = [{"name": p["player"]["name"], "number": p["player"].get("number"), "position": p["player"].get("pos")} for p in row.get("startXI", [])]
        if len(xi) == 11:
            claims.append(_claim(f"{t}.predicted_xi", "lineup", f"{names[t]} confirmed XI", xi, "/fixtures/lineups",
                                 "response[].startXI", now_iso, as_of=now_iso))
    od = client.get("/odds", fixture=fixture_id, bookmaker=8)
    raw["odds"] = od
    try:
        bet = next(b for b in od["response"][0]["bookmakers"][0]["bets"] if b["name"] == "Match Winner")
        m = {v["value"]: float(v["odd"]) for v in bet["values"]}
        for k, lab in (("odds_home", "Home"), ("odds_draw", "Draw"), ("odds_away", "Away")):
            claims.append(_claim(f"fixture.{k}", "odds", f"{lab} {m[lab]}", m[lab], "/odds", f"bets[Match Winner].values[{lab}]", now_iso))
    except (KeyError, IndexError, StopIteration, TypeError, ValueError):
        pass
    return claims, raw


def resolve(client: Client, home: str, away: str, date_from: str, date_to: str) -> list[dict]:
    """Candidate fixtures between two named teams in [date_from, date_to] (UTC dates)."""
    def team_ids(name):
        r = client.get("/teams", search=name)
        return [x["team"] for x in r.get("response", [])]
    hs, as_ = team_ids(home), team_ids(away)
    if not hs or not as_:
        return []
    out = []
    for h in hs[:3]:
        nxt = client.get("/fixtures", team=h["id"], next=10)
        for g in nxt.get("response", []):
            ids = {g["teams"]["home"]["id"], g["teams"]["away"]["id"]}
            if not ids & {a["id"] for a in as_[:3]}:
                continue
            d = g["fixture"]["date"][:10]
            if date_from <= d <= date_to:
                out.append({"fixture_id": g["fixture"]["id"], "home": g["teams"]["home"]["name"], "away": g["teams"]["away"]["name"],
                            "competition": g["league"]["name"], "kickoff": g["fixture"]["date"],
                            "venue": (g["fixture"].get("venue") or {}).get("name")})
    return out
