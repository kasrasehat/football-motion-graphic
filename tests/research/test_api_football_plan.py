"""API-Football on a restricted plan: resolve() avoids `next`, and plan refusals read as plan limits, not code errors."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tms.research import api_football as AF
from tms.research import cli as RC
from tests.fixtures.match.make_match_fixtures import CassetteClient, cassette, fx, wrap

pytestmark = pytest.mark.fast

NEXT_REFUSAL = "Free plans do not have access to the Next parameter."  # real answer, seen live on 2026-11-04
ARSENAL_TEAMS = wrap([{"team": {"id": 42, "name": "Arsenal"}}, {"team": {"id": 459, "name": "Arsenal Sarandi"}},
                      {"team": {"id": 1850, "name": "Arsenal W"}}])  # shape and ids of the real /teams answer
MADRID_TEAMS = wrap([{"team": {"id": 541, "name": "Real Madrid"}}, {"team": {"id": 7926, "name": "Real Madrid U19"}}])
TEAMS = {"/teams?search=Arsenal": ARSENAL_TEAMS, "/teams?search=Real Madrid": MADRID_TEAMS}
H2H = "/fixtures/headtohead?from=2026-12-09&h2h=42-541&to=2026-12-09"
GAME = fx(777, "2026-12-09T20:00:00+00:00", (42, "Arsenal"), (541, "Real Madrid"), None, None)


class RefusingClient(CassetteClient):
    """Cassette client that refuses the listed requests the way the API does on a restricted plan."""

    def __init__(self, cas, refuse=()):
        super().__init__(cas)
        self.refuse, self.asked, self.usage_file = tuple(refuse), [], None

    def get(self, path, **params):
        key = path + ("?" + "&".join(f"{k}={params[k]}" for k in sorted(params)) if params else "")
        self.asked.append(key)
        if self.refuse and key.startswith(self.refuse):
            raise AF.PlanRestricted("Free plans do not have access to this season, try from 2022 to 2024.")
        return super().get(path, **params)


class FakeResponse:
    headers = {}

    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


def _resolve(client):
    return AF.resolve(client, "Arsenal", "Real Madrid", "2026-12-09", "2026-12-09")


# ------------------------------------------------------------------ client
def test_plan_refusal_is_its_own_error_and_is_not_cached(monkeypatch, tmp_path):
    calls = []
    body = {"get": "fixtures", "errors": {"plan": NEXT_REFUSAL}, "results": 0, "response": []}
    monkeypatch.setattr(AF.httpx, "get", lambda url, **kw: calls.append(url) or FakeResponse(body))
    c = AF.Client(key="k", cache_dir=tmp_path)
    for _ in range(2):
        with pytest.raises(AF.PlanRestricted, match="Next parameter"):
            c.get("/fixtures", team=42, next=10)
    assert len(calls) == 2


@pytest.mark.parametrize("first", [
    FakeResponse({"errors": {"rateLimit": "Too many requests. Your rate limit is 10 requests per minute."}, "response": []}),  # real
    FakeResponse({}, status=429),  # real
])
def test_rate_limit_waits_and_retries(monkeypatch, tmp_path, first):
    waits, calls = [], []
    answers = [first, FakeResponse({"errors": [], "response": [1]})]
    monkeypatch.setattr(AF.httpx, "get", lambda url, **kw: calls.append(url) or answers[len(calls) - 1])
    d = AF.Client(key="k", cache_dir=tmp_path, sleep=waits.append).get("/fixtures", id=1)
    assert d["response"] == [1] and len(calls) == 2 and waits == [AF.RATE_LIMIT_WAIT_S]


def test_rate_limit_gives_up_after_the_retries(monkeypatch, tmp_path):
    waits = []
    monkeypatch.setattr(AF.httpx, "get", lambda url, **kw: FakeResponse({}, status=429))
    with pytest.raises(AF.QuotaExceeded):
        AF.Client(key="k", cache_dir=tmp_path, sleep=waits.append).get("/fixtures", id=1)
    assert len(waits) == AF.RATE_LIMIT_RETRIES


# ------------------------------------------------------------------ resolve
def test_resolve_never_uses_next_and_returns_the_fixture():
    c = RefusingClient({**TEAMS, H2H: wrap([GAME])})
    cands = _resolve(c)
    assert [(x["fixture_id"], x["home"], x["away"]) for x in cands] == [(777, "Arsenal", "Real Madrid")]
    assert not [k for k in c.asked if "next=" in k]


def test_resolve_prefers_the_exact_team_over_fuzzy_namesakes():
    c = RefusingClient({**TEAMS, H2H: wrap([GAME])})
    _resolve(c)
    assert [k for k in c.asked if "headtohead" in k] == [H2H]  # not Arsenal W, not Real Madrid U19


def test_resolve_falls_back_to_the_first_three_without_an_exact_name():
    teams = [{"id": i, "name": f"AEK Athens {i}"} for i in range(5)]
    assert [t["id"] for t in AF._pick_teams(teams, "AEK Athens")] == [0, 1, 2]


@pytest.mark.parametrize("game", [
    fx(778, "2026-12-10T20:00:00+00:00", (42, "Arsenal"), (541, "Real Madrid"), None, None),  # outside the window
    fx(779, "2026-12-09T20:00:00+00:00", (42, "Arsenal"), (33, "Manchester United"), None, None),  # other opponent
])
def test_resolve_keeps_only_those_two_teams_inside_the_window(game):
    c = RefusingClient({**TEAMS, H2H: wrap([game])})
    assert _resolve(c) == []


def test_resolve_with_no_meeting_in_the_window_is_no_match_and_asks_nothing_else():
    c = RefusingClient({**TEAMS, H2H: wrap([])}, refuse=["/fixtures?"])
    assert _resolve(c) == []  # real case: /fixtures?season=2026 is refused on Free even though h2h sees that season
    assert len([k for k in c.asked if k.startswith("/fixtures")]) == 1


def test_resolve_caps_several_teams_with_the_exact_name():
    teams = [{"id": i, "name": "Arsenal"} for i in range(5)]  # the real search finds more than one club named just this
    assert len(AF._pick_teams(teams, "Arsenal")) == 3


# ------------------------------------------------------------------ pull
def test_pull_keeps_the_rest_when_the_plan_refuses_one_part():
    c = RefusingClient(cassette(), refuse=["/injuries", "/odds"])
    claims, raw = AF.pull(c, 1234567, "2026-11-02T12:10:00Z")
    keys = {x["fact_key"] for x in claims}
    assert {"fixture.kickoff_utc", "H.form.last5", "h2h.last5"} <= keys
    assert "H.injuries" not in keys and "fixture.odds_home" not in keys  # refused is unknown, not "no absences"
    assert set(raw["_plan_refused"]) == {"injuries", "odds"}


def test_pull_reports_no_refusals_when_nothing_was_refused():
    assert "_plan_refused" not in AF.pull(RefusingClient(cassette()), 1234567, "2026-11-02T12:10:00Z")[1]


def test_pull_raises_when_the_fixture_itself_is_refused():
    with pytest.raises(AF.PlanRestricted):
        AF.pull(RefusingClient(cassette(), refuse=["/fixtures?id="]), 1234567, "2026-11-02T12:10:00Z")


def test_pull_names_the_current_manager_not_the_first_listed():
    claims, _ = AF.pull(RefusingClient(cassette()), 1234567, "2026-11-02T12:10:00Z")
    assert {x["fact_key"]: x["value"] for x in claims}["H.manager"] == "M. Coach"


def test_current_coach_needs_an_open_spell_at_this_team():
    gone = [{"name": "Z", "career": [{"team": {"id": 541}, "start": "2016-01-01", "end": "2018-05-01"},
                                     {"team": {"id": 9}, "start": "2019-01-01", "end": None}]}]
    assert AF._current_coach(gone, 541) is None


def test_pull_makes_no_injury_claim_before_any_are_filed():
    cas = cassette()
    cas["/injuries?fixture=1234567"] = wrap([])
    claims, _ = AF.pull(RefusingClient(cas), 1234567, "2026-11-02T12:10:00Z")
    assert "H.injuries" not in {x["fact_key"] for x in claims}


def test_pull_keeps_the_five_latest_played_meetings_without_asking_for_last():
    cas = cassette()
    games = [fx(100 + y, f"20{y}-03-01T20:00:00+00:00", (541, "Real Madrid"), (42, "Arsenal"), 1, 0) for y in range(10, 18)]
    cas["/fixtures/headtohead?h2h=541-42"] = wrap(games + [fx(1234567, "2026-11-02T20:00:00+00:00", (541, "Real Madrid"), (42, "Arsenal"), None, None)])
    claims, _ = AF.pull(RefusingClient(cas), 1234567, "2026-11-02T12:10:00Z")
    meetings = {x["fact_key"]: x["value"] for x in claims}["h2h.last5"]
    assert [m["date"][:4] for m in meetings] == ["2017", "2016", "2015", "2014", "2013"]


# ------------------------------------------------------------------ commands
def _stdout_json(text):
    return json.JSONDecoder().raw_decode(text)[0]


def test_fixture_resolve_says_the_plan_cannot_access_it(monkeypatch, capsys):
    monkeypatch.setattr(RC, "_client", lambda pr=None: RefusingClient(TEAMS, refuse=["/fixtures/headtohead"]))
    assert RC.cmd_resolve(SimpleNamespace(query="Arsenal vs Real Madrid 2026-12-09")) == 0
    text = capsys.readouterr().out
    out = _stdout_json(text)
    assert (out["mode"], out["api_status"], out["candidates"]) == ("web", "plan_restricted", [])
    assert "not an error in tms" in text and "plan cannot access" in text


def test_fixture_resolve_returns_the_fixture_when_the_plan_allows_it(monkeypatch, capsys):
    monkeypatch.setattr(RC, "_client", lambda pr=None: RefusingClient({**TEAMS, H2H: wrap([GAME])}))
    assert RC.cmd_resolve(SimpleNamespace(query="Arsenal vs Real Madrid 2026-12-09")) == 0
    out = _stdout_json(capsys.readouterr().out)
    assert out["mode"] == "api" and [x["fixture_id"] for x in out["candidates"]] == [777]


def _project(monkeypatch, tmp_path, client, fixture_id, method):
    brief = {"match": {"fixture_id": fixture_id, "resolution": {"method": method}}}
    pr = SimpleNamespace(dir=tmp_path, load_artifact=lambda name: brief)
    monkeypatch.setattr(RC.P, "load", lambda slug: pr)
    monkeypatch.setattr(RC.machine, "require_active", lambda pr, stage: None)
    monkeypatch.setattr(RC, "_client", lambda pr=None: client)
    return SimpleNamespace(project="x")


def test_research_api_skips_quietly_for_a_web_resolved_fixture(monkeypatch, tmp_path, capsys):
    client = RefusingClient({})
    assert RC.cmd_api(_project(monkeypatch, tmp_path, client, None, "web")) == 0
    assert "continue with web research" in capsys.readouterr().out
    assert client.asked == []


def test_research_api_falls_back_when_the_plan_refuses_the_fixture(monkeypatch, tmp_path, capsys):
    client = RefusingClient(cassette(), refuse=["/fixtures?id="])
    assert RC.cmd_api(_project(monkeypatch, tmp_path, client, 1234567, "api")) == 0
    text = capsys.readouterr().out
    assert "not an error in tms" in text and "continue with web research" in text
    assert not (tmp_path / "media" / "research" / "api_claims.json").exists()


def test_research_api_lists_the_parts_the_plan_refused(monkeypatch, tmp_path, capsys):
    client = RefusingClient(cassette(), refuse=["/odds"])
    assert RC.cmd_api(_project(monkeypatch, tmp_path, client, 1234567, "api")) == 0
    assert "plan refused odds" in capsys.readouterr().out
    assert (tmp_path / "media" / "research" / "api_claims.json").is_file()
