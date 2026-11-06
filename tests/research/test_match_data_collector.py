"""The standalone collector: contract, the rules for blocks and permission, and parsing that refuses bad rows."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import httpx
import jsonschema
import pytest

import match_data_collector
from match_data_collector.adapters.agent_facts import AgentFactsAdapter
from match_data_collector.adapters.ballhelper import BallhelperAdapter, find_team, league_rows, parse, row_adds_up
from match_data_collector.collector import Collector
from match_data_collector.contract import Fact, MatchQuery, Source
from match_data_collector.fetch import USER_AGENT, Blocked, NotPermitted, PoliteFetcher, RobotsDisallowed
from tms.research import api_football as AF
from tms.research.collect import ApiFootballAdapter

pytestmark = pytest.mark.fast

PKG = Path(match_data_collector.__file__).parent
BASE = "http://www.ballhelper.com"
LEAGUE = f"{BASE}/soccer-football/england-premier/england-premier-league.php"
HOME_PAGE = f'<a href="{LEAGUE}">England Prem.</a>'
ROW1 = "1 ARSENAL 9 8 0 1 14 5 4 0 0 9 2 4 0 1 5 3 24".split(" ")
ROW2 = "2 MANCHESTER CITY 9 7 0 2 20 10 4 0 1 11 7 3 0 1 9 3 21".replace("MANCHESTER CITY", "MANCHESTER_CITY").split(" ")
ROW3 = "3 BRIGHTON 9 6 1 2 24 7 3 1 0 13 1 3 0 2 11 6 19".split(" ")
ROW4 = "4 CHELSEA 9 5 1 3 19 15 3 1 1 13 9 2 0 2 6 6 16".split(" ")


def cells(*rows, join=False):
    tds = ["".join(f"<td>{c.replace('_', ' ')}</td>" for c in r) for r in rows]
    return "<tr>" + "".join(tds) + "</tr>" if join else "".join(f"<tr>{t}</tr>" for t in tds)


def league_page(rows=(ROW1, ROW2, ROW3, ROW4)):
    halves = "<tr><td>Arsenal</td><td>I&gt;</td><td>I&gt;</td><td>II&gt;</td><td>I=II</td></tr>"
    return (f"<p>England Premier league table, for season 2026/2027</p><p>Last updated: 11.5.2026</p><p>TABLE</p><table>{cells(*rows)}</table>"
            f"<p>Score more goals table as Home</p><table>{halves}</table><p>Score more goals table as Away</p><table>{halves}</table>")


def fetcher(pages: dict, robots=None, tmp=None):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        url = str(req.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=robots) if robots else httpx.Response(404)
        got = pages.get(url)
        if isinstance(got, int):
            return httpx.Response(got)
        return httpx.Response(200, text=got) if got is not None else httpx.Response(404)
    f = PoliteFetcher(cache_dir=tmp, transport=httpx.MockTransport(handler), sleep=lambda _s: None)
    f.seen = seen
    return f


def query(**kw):
    return MatchQuery(**{"home": "Arsenal", "away": "Real Madrid", "date": "2026-12-09", **kw})


def test_a_full_result_matches_the_published_schema_and_keeps_going_past_a_gap():
    f = fetcher({f"{BASE}/": HOME_PAGE, LEAGUE: league_page()})
    res = Collector([BallhelperAdapter(f)]).collect(query(home_league="Premier League")).to_dict()
    jsonschema.validate(json.loads(json.dumps(res)), json.loads((PKG / "schema" / "result.schema.json").read_text(encoding="utf-8")))
    by = {x["key"]: x for x in res["facts"]}
    assert by["home.league.points"]["value"] == 24 and by["home.league.home.goals_for"]["value"] == 9
    assert by["home.half_pattern.home"]["value"] == {"first": 2, "second": 1, "level": 1, "matches": 4}
    assert by["home.league.points"]["source"]["quote"].startswith("1 ARSENAL") and by["home.league.points"]["confidence"] == "low"
    assert by["home.league.page_note"]["as_of"] is None  # 11.5.2026 could be either month
    assert any(g["need"] == "away.league" and g["reason"] == "not_covered" for g in res["gaps"])


def test_sources_needing_permission_are_reported_and_never_requested():
    f = fetcher({})
    res = Collector([]).collect(query())
    assert {g.adapter for g in res.gaps if g.reason == "not_permitted"} == {"soccerway", "sofascore"}
    for url in ("https://us.soccerway.com/football/", "https://www.sofascore.com/", "https://example.com/"):
        with pytest.raises(NotPermitted):
            f.get_text(url)
    assert f.seen == []


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_a_block_stops_the_source_for_the_run_without_retrying(status):
    f = fetcher({LEAGUE: status})
    for _ in range(2):
        with pytest.raises(Blocked):
            f.get_text(LEAGUE)
    assert [str(r.url) for r in f.seen].count(LEAGUE) == 1


def test_a_verification_page_counts_as_a_block():
    f = fetcher({LEAGUE: "<title>x</title>Verifying you are human"})
    with pytest.raises(Blocked):
        f.get_text(LEAGUE)


def test_robots_is_obeyed_and_every_request_uses_the_one_honest_identity():
    f = fetcher({LEAGUE: "x"}, robots="User-agent: *\nDisallow: /soccer-football/\n")
    with pytest.raises(RobotsDisallowed):
        f.get_text(LEAGUE)
    assert [str(r.url) for r in f.seen] == [f"{BASE}/robots.txt"]
    assert {r.headers["user-agent"] for r in f.seen} == {USER_AGENT}


def test_the_fetcher_paces_requests_to_one_host():
    waits = []
    f = fetcher({LEAGUE: "ok", f"{BASE}/": "ok"})
    f.sleep, f.clock = waits.append, lambda: 100.0
    f.get_text(LEAGUE)
    f.get_text(f"{BASE}/")
    assert waits and all(w == 3.0 for w in waits)


def test_the_package_has_no_dependency_on_its_host_project():
    for path in PKG.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n == "tms" or n.startswith("tms.") for n in names), path


def test_a_row_joined_by_a_missing_close_tag_is_split():
    page = parse(f"<table>{cells(ROW1, ROW2, join=True)}{cells(ROW3, ROW4)}</table>")
    assert [r["team"] for r in league_rows(page)] == ["ARSENAL", "MANCHESTER CITY", "BRIGHTON", "CHELSEA"]


def test_a_row_that_does_not_add_up_becomes_a_gap_not_a_fact():
    bad = list(ROW1)
    bad[-1] = "99"
    f = fetcher({f"{BASE}/": HOME_PAGE, LEAGUE: league_page((bad, ROW2, ROW3, ROW4))})
    res = Collector([BallhelperAdapter(f)]).collect(query(home_league="England Prem."))
    assert not res.facts and any(g.reason == "parse_mismatch" for g in res.gaps)
    assert not row_adds_up(league_rows(parse(league_page((bad, ROW2, ROW3, ROW4))))[0])


def test_team_names_match_only_when_unambiguous():
    assert find_team(["ARSENAL", "CHELSEA"], "Arsenal FC") == ("ARSENAL", "")
    assert find_team(["MANCHESTER CITY", "MANCHESTER UTD"], "Manchester") == (None, "ambiguous")
    assert find_team(["ARSENAL"], "Real Madrid") == (None, "not_found")


def test_one_adapter_crashing_costs_only_its_own_facts():
    class Boom:
        name = "boom"

        def collect(self, q, now):
            raise RuntimeError("bug")

    class Good:
        name = "good"

        def collect(self, q, now):
            return [Fact("fixture.venue", "X", "Venue X.", Source("good", "api", now))], []
    res = Collector([Boom(), Good()]).collect(query())
    assert [f.key for f in res.facts] == ["fixture.venue"] and any(g.adapter == "boom" and g.reason == "unavailable" for g in res.gaps)


def test_agent_facts_without_a_source_are_rejected(tmp_path):
    good = {"key": "home.news", "value": "x", "statement": "A sourced line.", "source": {"url": "https://a.example/", "quote": "q", "retrieved_at": "t"}}
    p = tmp_path / "facts.json"
    p.write_text(json.dumps({"facts": [good, {"key": "home.rumour", "value": "y", "statement": "No source."}]}), encoding="utf-8")
    facts, gaps = AgentFactsAdapter(p).collect(query(), "t")
    assert [f.key for f in facts] == ["home.news"] and [(g.need, g.reason) for g in gaps] == [("home.rumour", "invalid_input")]


class FakeClient:
    available = True


def test_api_football_claims_map_to_the_contract(monkeypatch):
    claim = {"fact_key": "H.manager", "value": "Mikel Arteta", "statement": "Manager.", "unit": None, "as_of": None, "confidence": "high",
             "sources": [{"kind": "api", "endpoint": "/coachs", "field_path": "response[0].name", "retrieved_at": "t"}]}
    monkeypatch.setattr(AF, "pull", lambda _c, fid, _n: ([claim], {"fid": fid}))
    facts, gaps = ApiFootballAdapter(FakeClient()).collect(query(ids={"api_football_fixture": "7"}), "t")
    assert not gaps and facts[0].key == "home.manager" and facts[0].source.endpoint == "/coachs"


@pytest.mark.parametrize("exc,reason", [(AF.QuotaExceeded("over"), "quota"), (AF.ApiError("Free plans do not have access"), "plan_limited"), (AF.ApiError("down"), "unavailable")])
def test_api_football_failures_become_gaps(monkeypatch, exc, reason):
    def boom(*_a):
        raise exc
    monkeypatch.setattr(AF, "pull", boom)
    facts, gaps = ApiFootballAdapter(FakeClient()).collect(query(ids={"api_football_fixture": "7"}), "t")
    assert not facts and gaps[0].reason == reason


def test_parts_the_plan_refused_are_reported_as_gaps(monkeypatch):
    monkeypatch.setattr(AF, "pull", lambda _c, _f, _n: ([], {"_plan_refused": {"form": "Free plans do not have access to the Last parameter"}}))
    _, gaps = ApiFootballAdapter(FakeClient()).collect(query(ids={"api_football_fixture": "7"}), "t")
    assert [(g.need, g.reason) for g in gaps] == [("form", "plan_limited")]
