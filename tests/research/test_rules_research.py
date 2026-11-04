"""M8: WC / MD / MA rules, dossier merge, API client behaviour (cassette, cache, quota), query parsing."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tms.predict import config as predict_config
from tms.research import api_football as AF
from tms.research import facts as FX
from tms.research.dossier import merge, parse_query
from tms.validate.registry import Context
from tests.helpers import FIX, expect_clean, expect_violation, findings, fixture, rule_ids

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


# ------------------------------------------------------------------ single_source flag reaches the fact status
def _merge(*web_claims, api=()):
    return merge("fx-match", fixture("brief.match"), list(api), {"claims": list(web_claims)}, "2026-11-02T12:30:00Z", {}, len(api))


def _flag(claim):
    return {**claim, "single_source": True}


def _flagged_injuries_with_second_cited_source():
    """The researcher flags the claim: the second cited page exists but prints something different."""
    c = _flag(_web("W-001", "H.injuries", [], "https://www.uefa.com/a", 1))
    c["sources"].append({**c["sources"][0], "url": "https://www.marca.com/b", "quote": "a different squad list"})
    return c


def test_merge_flagged_claim_is_single_source_despite_a_second_cited_domain():
    d = _merge(_flagged_injuries_with_second_cited_source())
    assert d["facts"]["H.injuries"]["status"] == "single_source"


def test_MA04_flagged_key_fact_must_be_stated_as_uncertain():
    dossier = _merge(_flagged_injuries_with_second_cited_source())
    a = fixture("match_analysis")
    a["uncertainties"] = []
    expect_violation("MA-04", "match_analysis", a, ctx(match_dossier=dossier))
    a["uncertainties"] = ["The injury list rests on one source."]
    assert "MA-04" not in rule_ids("match_analysis", a, ctx(match_dossier=dossier))


def test_merge_flag_on_any_claim_marks_the_fact():
    web = [_web("W-001", "H.xg_for_avg", 2.10, "https://fbref.com/a", 2), _flag(_web("W-002", "H.xg_for_avg", 2.13, "https://understat.com/b", 2))]
    d = _merge(*web)
    assert d["facts"]["H.xg_for_avg"]["status"] == "single_source" and d["conflicts"] == []


def test_merge_flagged_claim_keeps_an_unresolved_conflict_blocking():
    """The prediction model drops facts with status `conflict` and MD-04 blocks them: a flag must not hide that."""
    web = [_flag(_web("W-001", "H.xg_for_avg", 2.1, "https://fbref.com/a", 2)), _web("W-002", "H.xg_for_avg", 1.4, "https://understat.com/b", 2)]
    d = _merge(*web)
    assert d["facts"]["H.xg_for_avg"]["status"] == "conflict"
    assert d["conflicts"] == [{"fact_key": "H.xg_for_avg", "claim_ids": ["C-001", "C-002"], "resolution": None}]
    expect_violation("MD-04", "match_dossier", d, ctx())


def test_merge_flagged_fact_with_resolved_conflict_reaches_MA04_and_keeps_the_resolution():
    web = [_flag(_web("W-001", "H.injuries", [], "https://www.uefa.com/a", 1)),
           _web("W-002", "H.injuries", [{"player": "Someone", "reason": "knock"}], "https://random-blog.example/b", 3)]
    d = _merge(*web)
    assert d["facts"]["H.injuries"]["status"] == "single_source"
    assert d["conflicts"] == [{"fact_key": "H.injuries", "claim_ids": ["C-001", "C-002"], "resolution": "higher-tier source preferred"}]
    a = fixture("match_analysis")
    a["uncertainties"] = []
    expect_violation("MA-04", "match_analysis", a, ctx(match_dossier=d))


def test_merge_flagged_web_claim_behind_api_value_keeps_api_value_and_resolution():
    d = _merge(_flag(_web("W-001", "H.goals_for_avg", 2.9, "https://fbref.com/a", 2)), api=[_api_claim("H.goals_for_avg", 2.3)])
    f = d["facts"]["H.goals_for_avg"]
    assert (f["value"], f["status"]) == (2.3, "single_source")
    assert d["conflicts"][0]["resolution"] == "API data preferred"


# ------------------------------------------------------------------ fixture.league_avg_goals definition
def test_MD01_league_avg_range_is_the_models_range():
    assert FX.spec("fixture.league_avg_goals")["range"] == predict_config()["strengths"]["league_avg_range"]


@pytest.mark.parametrize("value", [0.6, 1.40, 2.4])
def test_MD01_league_avg_per_team_value_accepted(value):
    d = fixture("match_dossier")
    d["facts"]["fixture.league_avg_goals"] = {"value": value, "unit": None, "claim_ids": ["C-001"], "status": "single_source", "as_of": None}
    assert not [f for f in findings("match_dossier", d, ctx()) if f.rule == "MD-01"]


@pytest.mark.parametrize("value", [0.5, 2.5, 3.92])
def test_MD01_league_avg_per_match_total_rejected(value):
    d = fixture("match_dossier")
    d["facts"]["fixture.league_avg_goals"] = {"value": value, "unit": None, "claim_ids": ["C-001"], "status": "single_source", "as_of": None}
    expect_violation("MD-01", "match_dossier", d, ctx())


# ------------------------------------------------------------------ domain(): the unit of corroboration
@pytest.mark.parametrize("url,expected", [
    ("https://uefa.com/a", "uefa.com"),
    ("https://www.uefa.com/a", "uefa.com"),
    ("https://match.uefa.com/a", "uefa.com"),
    ("https://standings.uefa.com/a", "uefa.com"),
    ("https://A.B.UEFA.com:443/a", "uefa.com"),
    ("https://www.uefa.com./a", "uefa.com"),
    ("https://sportsmole.co.uk/a", "sportsmole.co.uk"),
    ("https://www.sportsmole.co.uk/a", "sportsmole.co.uk"),
    ("https://news.sportsmole.co.uk/a", "sportsmole.co.uk"),
    ("https://sport.bbc.co.uk/a", "bbc.co.uk"),
    ("https://www.ole.com.ar/a", "ole.com.ar"),
    ("https://www.abc.net.au/a", "abc.net.au"),
    ("https://en.as.com/a", "as.com"),
    ("https://sport.goal.co/a", "goal.co"),
    ("https://sport.sky.it/a", "sky.it"),
    ("http://localhost:3000/a", "localhost"),
    ("http://10.0.3.4/a", "10.0.3.4"),
])
def test_domain_is_the_registrable_domain(url, expected):
    assert FX.domain(url) == expected


def test_merge_subdomains_of_one_site_are_one_source():
    c = _web("W-001", "H.injuries", [], "https://www.uefa.com/a", 1)
    c["sources"] += [{**c["sources"][0], "url": "https://match.uefa.com/b"}, {**c["sources"][0], "url": "https://standings.uefa.com/c"}]
    assert _merge(c)["facts"]["H.injuries"]["status"] == "single_source"


def test_merge_two_publishers_under_one_multi_part_suffix_are_independent():
    c = _web("W-001", "H.injuries", [], "https://www.sportsmole.co.uk/a", 3)
    c["sources"].append({**c["sources"][0], "url": "https://www.bbc.co.uk/b", "tier": 1})
    assert _merge(c)["facts"]["H.injuries"]["status"] == "agreed"


def _with_xi_sources(*urls):
    d = fixture("match_dossier")
    c = next(c for c in d["claims"] if c["fact_key"] == "H.predicted_xi")
    c["sources"] = [{**c["sources"][0], "url": u} for u in urls]
    return d


@pytest.mark.parametrize("urls", [("https://www.uefa.com/a", "https://match.uefa.com/b"),
                                  ("https://www.sportsmole.co.uk/a", "https://news.sportsmole.co.uk/b")])
def test_MD02_subdomains_do_not_corroborate(urls):
    expect_violation("MD-02", "match_dossier", _with_xi_sources(*urls), ctx())


def test_MD02_two_publishers_under_one_multi_part_suffix_corroborate():
    assert "MD-02" not in rule_ids("match_dossier", _with_xi_sources("https://www.sportsmole.co.uk/a", "https://www.bbc.co.uk/b"), ctx())


@pytest.mark.parametrize("url,tier", [
    ("https://www.uefa.com/a", 1), ("https://match.uefa.com/a", 1), ("https://www.bbc.co.uk/sport", 1), ("https://sport.bbc.co.uk/a", 1),
    ("https://www.as.com/a", 1), ("https://fbref.com/a", 2), ("https://www.fbref.com/a", 2),
    ("https://www.sportsmole.co.uk/a", 3), ("https://notuefa.com/a", 3), ("https://notbbc.co.uk/a", 3), ("https://uefa.com.evil.example/a", 3),
])
def test_tier_of_matches_listed_sites_and_their_subdomains(url, tier):
    assert FX.tier_of(url) == tier


def test_tier_of_honours_an_entry_below_the_registrable_domain(monkeypatch):
    """Tier lists match the full host, so a list entry may name one section of a site."""
    monkeypatch.setattr(FX, "sources", lambda: {"tier1": ["sport.example.co.uk"], "tier2": [], "blocked": [], "cc_second_level": ["co"]})
    assert FX.tier_of("https://sport.example.co.uk/a") == 1
    assert FX.tier_of("https://live.sport.example.co.uk/a") == 1
    assert FX.tier_of("https://example.co.uk/a") == 3


@pytest.mark.parametrize("url,is_blocked", [
    ("https://old.reddit.com/r/a", True), ("https://mobile.x.com/a", True), ("https://www.youtube.com/a", True),
    ("https://netflix.com/a", False), ("https://www.uefa.com/a", False),
])
def test_blocked_matches_listed_sites_and_their_subdomains(url, is_blocked):
    assert FX.blocked(url) is is_blocked


# ------------------------------------------------------------------ required levels of the fact registry
def test_required_keys_skip_optional_facts_and_keep_levels():
    per_team = {"manager": "warning", "formation": "warning", "standing.position": "warning", "form.last5": "error",
                "goals_for_avg": "error", "goals_against_avg": "error", "xg_for_avg": "warning", "xg_against_avg": "warning",
                "injuries": "error", "suspensions": "warning", "predicted_xi": "error", "key_players": "warning", "tactics.*": "error"}
    assert dict(FX.required_keys()) == {
        "fixture.kickoff_utc": "error", "fixture.venue": "error", "fixture.competition": "error", "fixture.stakes": "warning",
        "h2h.last5": "warning", **{f"{t}.{k}": level for t in "HA" for k, level in per_team.items()}}


def test_required_levels_in_the_registry_are_known():
    for key, sp in FX.config()["facts"].items():
        assert sp.get("required", "no") in ("error", "warning", "no", False), key


def test_required_keys_accept_both_spellings_of_no(monkeypatch):
    facts = {"a.bare": {"required": False}, "a.quoted": {"required": "no"}, "a.absent": {}, "a.kept": {"required": "warning"}}
    monkeypatch.setattr(FX, "config", lambda: {"facts": facts})
    assert FX.required_keys() == [("a.kept", "warning")]


def _md06(doc):
    return {f.location: f.severity for f in findings("match_dossier", doc, ctx()) if f.rule == "MD-06"}


def test_MD06_missing_optional_facts_stay_silent():
    optional = ("fixture.round", "fixture.referee", "fixture.league_avg_goals", "fixture.home_advantage", "fixture.odds_home",
                "H.possession_avg", "A.clean_sheets", "H.standing.points", "A.shots_avg", "H.home_goals_for_avg", "A.away_goals_against_avg")
    d = fixture("match_dossier")
    for key in optional:
        d["facts"].pop(key, None)
    assert not set(_md06(d)) & set(optional)


@pytest.mark.parametrize("key,severity", [("fixture.stakes", "warning"), ("H.xg_for_avg", "warning"), ("A.suspensions", "warning"),
                                          ("fixture.venue", "error"), ("A.form.last5", "error"), ("H.predicted_xi", "error")])
def test_MD06_severity_follows_the_required_level(key, severity):
    d = fixture("match_dossier")
    assert key not in _md06(d)
    del d["facts"][key]
    assert _md06(d)[key] == severity


def test_MD06_missing_tactics_prefix_is_an_error():
    d = fixture("match_dossier")
    assert "H.tactics.*" not in _md06(d)
    d["facts"] = {k: f for k, f in d["facts"].items() if not k.startswith("H.tactics.")}
    assert _md06(d)["H.tactics.*"] == "error"
