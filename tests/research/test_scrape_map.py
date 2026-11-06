"""A collector report becoming dossier facts, using a trimmed real report (Newcastle v Everton, collected after the match)."""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from match_collector.models import CollectionReport

from tests.helpers import fixture
from tms import validate as V
from tms.predict import strengths
from tms.research.dossier import merge
from tms.research.scrape_map import map_report, same_team
from tms.validate.registry import Context

pytestmark = pytest.mark.fast

RAW = json.loads((Path(__file__).parents[1] / "fixtures" / "match" / "collector_report.json").read_text(encoding="utf-8"))
BRIEF = {"match": {"home": "Newcastle United", "away": "Everton FC"}}
BEFORE_KICKOFF = datetime(2026, 11, 2, 12, tzinfo=UTC)


def report(edit=None, finished=BEFORE_KICKOFF):
    d = copy.deepcopy(RAW)
    if edit:
        edit(d)
    r = CollectionReport.model_validate(d)
    r.finished_at = finished
    return r


def facts(m):
    return {c["fact_key"]: c for c in m["claims"]}


def test_rates_keep_their_sample_and_each_team_is_on_the_right_side():
    f = facts(map_report(report(), BRIEF))
    assert f["H.goals_for_avg"]["value"] == 1.5 and f["A.goals_against_avg"]["value"] == 1.12  # 12/8 and 9/8
    assert "12 goals in 8 games" in f["H.goals_for_avg"]["statement"]
    home = f["H.split.home"]["value"]
    assert home["played"] == 4 and sum(home["wdl"].values()) == 4 and home["ht_ft_sample"] == 4 and "event_ids" not in home


def test_form_is_oldest_first_and_every_claim_points_back_into_the_report():
    m = map_report(report(), BRIEF)
    assert facts(m)["H.form.last5"]["value"] == ["L", "W", "L", "L", "W"]  # the source lists W L L W L, newest first
    for c in m["claims"]:
        s = c["sources"][0]
        assert s["kind"] == "collector" and s["run_id"] == RAW["run_id"] and s["field_path"].startswith("sources[soccerway].") and s["url"]


def test_only_real_meetings_before_kick_off_count_as_head_to_head():
    rows = facts(map_report(report(), BRIEF))["h2h.last5"]["value"]
    assert rows and all(r["date"] < "2026-11-02" for r in rows)  # not this match itself
    assert {r["home"] for r in rows} <= {"Newcastle", "Everton"}  # the tab also lists games against other clubs


def test_a_table_collected_before_kick_off_is_used_and_one_collected_after_is_not():
    before = map_report(report(), BRIEF)
    assert facts(before)["H.standing.points"]["value"] == 11
    after = map_report(report(finished=datetime(2026, 11, 6, tzinfo=UTC)), BRIEF)
    assert "H.standing.points" not in facts(after)
    assert any(g["need"] == "H.standing" and "after kick-off" in g["why"] for g in after["gaps"])


def test_a_table_row_that_does_not_add_up_becomes_a_gap():
    def edit(d):
        rows = d["sources"][0]["data"]["standings"][0]["value"]["rows"]
        for r in rows:
            r["text"] = r["text"].replace("Newcastle 9", "Newcastle 12")
    m = map_report(report(edit), BRIEF)
    assert "H.standing.points" not in facts(m) and any("does not add up" in g["why"] for g in m["gaps"])


def test_a_results_sample_running_past_kick_off_is_not_used():
    def edit(d):
        d["sources"][0]["data"]["team_analysis"][0]["value"]["before_kickoff"] = "2026-11-05T00:00:00+00:00"
    m = map_report(report(edit), BRIEF)
    assert "H.goals_for_avg" not in facts(m) and any("past kick-off" in g["why"] for g in m["gaps"])


def test_no_games_is_unknown_but_a_real_zero_stays_zero():
    def edit(d):
        team = d["sources"][0]["data"]["team_analysis"][0]["value"]["teams"][0]
        team["splits"]["home"]["played"] = 0
        team["splits"]["overall"]["goals_for"] = 0
    m = map_report(report(edit), BRIEF)
    f = facts(m)
    assert "H.split.home" not in f and any(g["need"] == "H.split.home" for g in m["gaps"])
    assert f["H.goals_for_avg"]["value"] == 0


def test_venue_rates_need_enough_games():
    assert "H.home_goals_for_avg" not in facts(map_report(report(), BRIEF))  # 4 home games is too few for the model

    def edit(d):
        for side in d["sources"][0]["data"]["team_analysis"][0]["value"]["teams"]:
            side["splits"]["home"]["played"] = 5
    assert facts(map_report(report(edit), BRIEF))["H.home_goals_for_avg"]["value"] > 0


def test_a_wrong_date_gives_no_facts_and_says_why():
    def edit(d):
        d["sources"][0]["match"]["date_verified"] = False
    m = map_report(report(edit), BRIEF)
    assert not m["claims"] and any(g["source"] == "soccerway" and g["need"] == "all" for g in m["gaps"])


def test_home_and_away_swapped_against_the_brief_gives_no_facts():
    m = map_report(report(), {"match": {"home": "Everton", "away": "Newcastle"}})
    assert not m["claims"] and any("check the fixture" in g["why"] for g in m["gaps"])


def test_a_blocked_source_leaves_a_gap_and_costs_nothing_else():
    m = map_report(report(), BRIEF)
    assert any(g["source"] == "sofascore" and "403" in g["why"] for g in m["gaps"]) and facts(m)["H.goals_for_avg"]


def test_team_name_matching():
    assert same_team("Newcastle Utd", "Newcastle United") and same_team("Everton FC", "Everton")
    assert not same_team("Everton", "Arsenal")


def test_claims_reach_the_dossier_and_feed_the_goals_model():
    brief = fixture("brief.match")
    brief["match"].update(home="Newcastle", away="Everton", kickoff_utc="2026-11-02T20:00:00Z")
    doc = merge("fx", brief, [], None, "2026-11-02T13:00:00Z", {"brief": "0" * 64, "collector_claims": "1" * 64}, 0, map_report(report(), brief)["claims"])
    assert doc["facts"]["H.goals_for_avg"]["value"] == 1.5 and {c["origin"] for c in doc["claims"]} == {"collector"}
    assert not [f for f in V.validate_doc("match_dossier", doc, Context(mode="match_preview", artifacts={"brief": brief}))
                if f.severity == "error" and f.rule == "SCHEMA"]
    s = strengths.compute(doc["facts"])
    assert s.lam_home > 0 and s.lam_away > 0 and ("H.goals_for_avg", 1.5) in s.inputs_used


def test_kick_off_from_the_collector_and_one_other_domain_corroborates_a_key_fact():
    brief = fixture("brief.match")
    brief["match"].update(home="Newcastle", away="Everton", kickoff_utc="2026-11-02T20:00:00Z")
    ko = {"id": "W-001", "fact_key": "fixture.kickoff_utc", "category": "fixture", "statement": "Kick-off.", "value": "2026-11-02T20:00:00Z", "unit": None,
          "as_of": None, "confidence": "high", "sources": [{"kind": "web", "url": "https://www.bbc.com/x", "title": "t", "publisher": "BBC", "tier": 1, "quote": "q", "retrieved_at": "2026-11-02T12:00:00Z"}]}
    doc = merge("fx", brief, [], {"claims": [ko]}, "2026-11-02T13:00:00Z", {"brief": "0" * 64, "collector_claims": "1" * 64}, 0, map_report(report(), brief)["claims"])
    found = V.validate_doc("match_dossier", doc, Context(mode="match_preview", artifacts={"brief": brief, "web_claims": {"claims": [ko]}}))
    assert not [f for f in found if f.rule == "MD-02" and f.location == "fixture.kickoff_utc"]


def test_collector_sources_cannot_be_typed_into_web_claims():
    w = fixture("web_claims")
    w["claims"][0]["sources"] = [{"kind": "collector", "url": "https://x.example/", "publisher": "p", "tier": 3, "field_path": "a", "run_id": "r",
                                  "retrieved_at": "2026-11-02T12:00:00Z"}]
    found = V.validate_doc("web_claims", w, Context(mode="match_preview", artifacts={}))
    assert any(f.rule == "WC-01" and "tms research scrape" in f.message for f in found)
