"""M8: WC / MD / MA rules, dossier merge, API client behaviour (cassette, cache, quota), query parsing."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tms.research import api_football as AF
from tms.research.dossier import merge, parse_query
from tms.validate.registry import Context
from tests.helpers import FIX, expect_clean, expect_violation, fixture

pytestmark = pytest.mark.fast
NOW = datetime(2026, 11, 2, 12, 40, tzinfo=timezone.utc)
MATCH = FIX / "match"


def spec():
    return json.loads((MATCH / "tactic_spec.json").read_text(encoding="utf-8"))


def ctx(**over):
    arts = {"brief": fixture("brief.match"), "match_dossier": fixture("match_dossier"), "tactic_spec": spec(),
            "match_analysis": fixture("match_analysis"), "web_claims": fixture("web_claims")}
    arts.update(over)
    return Context(mode="match_preview", now=NOW, artifacts=arts)


def test_fixtures_clean():
    for name in ("web_claims", "match_dossier", "match_analysis"):
        expect_clean(name, fixture(name), ctx())


# ------------------------------------------------------------------ WC
def test_WC01_social_media_source():
    d = fixture("web_claims")
    d["claims"][0]["sources"][0]["url"] = "https://x.com/someone/status/1"
    expect_violation("WC-01", "web_claims", d, ctx())


def test_WC02_bad_value_type():
    d = fixture("web_claims")
    d["claims"][0]["value"] = 9.5  # xG per match outside plausible range
    expect_violation("WC-02", "web_claims", d, ctx())


def test_WC03_overclaimed_tier():
    d = fixture("web_claims")
    d["claims"][0]["sources"][0]["url"] = "https://random-blog.example/xg"
    d["claims"][0]["sources"][0]["tier"] = 1
    expect_violation("WC-03", "web_claims", d, ctx())


def test_WC04_duplicate_ids():
    d = fixture("web_claims")
    d["claims"][1]["id"] = d["claims"][0]["id"]
    expect_violation("WC-04", "web_claims", d, ctx())


# ------------------------------------------------------------------ MD
def test_MD01_implausible_fact():
    d = fixture("match_dossier")
    d["facts"]["H.goals_for_avg"]["value"] = 11.0
    expect_violation("MD-01", "match_dossier", d, ctx())


def test_MD02_key_fact_single_web_source():
    d = fixture("match_dossier")
    c = next(c for c in d["claims"] if c["fact_key"] == "H.predicted_xi")
    c["sources"] = c["sources"][:1]
    expect_violation("MD-02", "match_dossier", d, ctx())


def test_MD03_stale_team_news():
    d = fixture("match_dossier")
    d["facts"]["H.injuries"]["as_of"] = "2026-10-28T12:00:00Z"
    expect_violation("MD-03", "match_dossier", d, ctx())


def test_MD04_unresolved_conflict():
    d = fixture("match_dossier")
    d["conflicts"] = [{"fact_key": "H.xg_for_avg", "claim_ids": ["C-038", "C-039"], "resolution": None}]
    expect_violation("MD-04", "match_dossier", d, ctx())


def test_MD05_wrong_fixture():
    d = fixture("match_dossier")
    d["fixture"]["away"] = "Chelsea"
    expect_violation("MD-05", "match_dossier", d, ctx())


def test_MD06_missing_required_fact():
    d = fixture("match_dossier")
    del d["facts"]["A.form.last5"]
    expect_violation("MD-06", "match_dossier", d, ctx())


def test_MD07_thin_coverage():
    d = fixture("match_dossier")
    d["coverage"]["tactics"] = 1
    expect_violation("MD-07", "match_dossier", d, ctx())


# ------------------------------------------------------------------ MA
def test_MA01_ref_not_in_dossier():
    d = fixture("match_analysis")
    d["sections"][0]["assertions"][0]["refs"] = ["H.made_up_stat"]
    expect_violation("MA-01", "match_analysis", d, ctx())


def test_MA02_battle_player_not_in_xi():
    s = spec()
    hp = fixture("match_analysis")["key_battles"][0]["home_player"]
    next(p for p in s["teams"]["H"]["players"] if p["id"] == hp)["name"] = "Someone Else"
    expect_violation("MA-02", "match_analysis", fixture("match_analysis"), ctx(tactic_spec=s))


def test_MA03_unused_principle():
    d = fixture("match_analysis")
    d["tactical_battles"] = d["tactical_battles"][:1]
    expect_violation("MA-03", "match_analysis", d, ctx())


def test_MA04_missing_outlook():
    d = fixture("match_analysis")
    d["sections"] = [s for s in d["sections"] if s["id"] != "outlook"]
    expect_violation("MA-04", "match_analysis", d, ctx())


# ------------------------------------------------------------------ merge behaviour
def _api_claim(key, value):
    return {"fact_key": key, "category": "team_stats", "statement": key, "value": value, "unit": None, "as_of": None, "confidence": "high",
            "origin": "api", "sources": [{"kind": "api", "endpoint": "/teams/statistics", "field_path": "x", "retrieved_at": "2026-11-02T12:00:00Z"}]}


def _web(id_, key, value, url, tier):
    return {"id": id_, "fact_key": key, "category": "xg", "statement": key, "value": value, "unit": None, "as_of": None, "confidence": "medium",
            "sources": [{"kind": "web", "url": url, "title": "t", "publisher": "p", "tier": tier, "quote": "q", "retrieved_at": "2026-11-02T12:00:00Z"}]}


def test_merge_prefers_api_and_records_resolution():
    web = {"claims": [_web("W-001", "H.goals_for_avg", 2.9, "https://fbref.com/a", 2)]}
    d = merge("fx-match", fixture("brief.match"), [_api_claim("H.goals_for_avg", 2.3)], web, "2026-11-02T12:30:00Z", {}, 1)
    assert d["facts"]["H.goals_for_avg"]["value"] == 2.3
    assert d["facts"]["H.goals_for_avg"]["status"] == "resolved_conflict"
    assert d["conflicts"][0]["resolution"] == "API data preferred"


def test_merge_flags_equal_tier_disagreement_as_conflict():
    web = {"claims": [_web("W-001", "H.xg_for_avg", 2.1, "https://fbref.com/a", 2), _web("W-002", "H.xg_for_avg", 1.4, "https://understat.com/b", 2)]}
    d = merge("fx-match", fixture("brief.match"), [], web, "2026-11-02T12:30:00Z", {}, 0)
    assert d["facts"]["H.xg_for_avg"]["status"] == "conflict" and d["conflicts"][0]["resolution"] is None
    assert d["data_mode"] == "web"


def test_merge_agreement_within_tolerance():
    web = {"claims": [_web("W-001", "H.xg_for_avg", 2.10, "https://fbref.com/a", 2), _web("W-002", "H.xg_for_avg", 2.13, "https://understat.com/b", 2)]}
    d = merge("fx-match", fixture("brief.match"), [], web, "2026-11-02T12:30:00Z", {}, 0)
    assert d["facts"]["H.xg_for_avg"]["status"] == "agreed" and d["conflicts"] == []


# ------------------------------------------------------------------ API client
class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self._b, self.status_code, self.headers = body, status, headers or {}

    def json(self):
        return self._b


def test_client_caches_and_enforces_project_budget(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(AF.httpx, "get", lambda url, **kw: calls.append(url) or FakeResponse({"errors": [], "response": [1]}))
    c = AF.Client(key="k", cache_dir=tmp_path / "c", max_calls=2, usage_file=tmp_path / "usage.json")
    c.get("/teams", search="Arsenal")
    c.get("/teams", search="Arsenal")  # cached: no new call
    assert len(calls) == 1
    c.get("/teams", search="Madrid")
    with pytest.raises(AF.QuotaExceeded):
        c.get("/teams", search="Chelsea")
    assert json.loads((tmp_path / "usage.json").read_text())["calls"] == 2


def test_client_reports_api_quota_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(AF.httpx, "get", lambda url, **kw: FakeResponse({"errors": {"requests": "You have reached the request limit for the day"}, "response": []}))
    with pytest.raises(AF.QuotaExceeded):
        AF.Client(key="k", cache_dir=tmp_path).get("/fixtures", id=1)


def test_client_without_key_is_unavailable(monkeypatch, tmp_path):
    c = AF.Client(key="", cache_dir=tmp_path)
    assert not c.available
    with pytest.raises(AF.ApiError, match="web-only"):
        c.get("/status")


def test_resolve_and_pull_from_cassette():
    from tests.fixtures.match.make_match_fixtures import CassetteClient, cassette
    cl = CassetteClient(cassette())
    cands = AF.resolve(cl, "Real Madrid", "Arsenal", "2026-11-02", "2026-11-03")
    assert [c["fixture_id"] for c in cands] == [1234567]
    claims, raw = AF.pull(CassetteClient(cassette()), 1234567, "2026-11-02T12:10:00Z")
    keys = {c["fact_key"] for c in claims}
    assert {"fixture.kickoff_utc", "H.form.last5", "A.goals_for_avg", "h2h.last5", "H.injuries", "fixture.odds_home"} <= keys


@pytest.mark.parametrize("q,home,away,d0", [
    ("Real Madrid vs Arsenal tonight", "Real Madrid", "Arsenal", "2026-11-02"),
    ("Arsenal v Chelsea tomorrow", "Arsenal", "Chelsea", "2026-11-03"),
    ("Inter - Milan 2026-11-09", "Inter", "Milan", "2026-11-09"),
])
def test_parse_query(q, home, away, d0):
    r = parse_query(q, datetime(2026, 11, 2, 9, 0))
    assert (r["home"], r["away"], r["date_from"]) == (home, away, d0)


def test_parse_query_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_query("tell me about Madrid", datetime(2026, 11, 2))
