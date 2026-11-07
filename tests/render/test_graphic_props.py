"""Engine side of the graphics (no rendering): the line-up board's rows come from the tactic spec by shirt number, run
arrows take the running player's team colour. The renderer's half is in render/test/graphics.test.ts."""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest
from match_collector.models import CollectionReport

from tests.helpers import FIX, fixture
from tms import schema
from tms.choreo.document import build_doc
from tms.props.builder import _graphic_data, _overlay_style, build, resolve_ref
from tms.research.dossier import merge
from tms.research.scrape_map import map_report
from tms.tactic.still import still_props
from tms.timeline import provisional

pytestmark = pytest.mark.fast
M = FIX / "match"


def _load(name: str):
    return json.loads((M / f"{name}.json").read_text(encoding="utf-8"))


def _board():
    return next(s for s in _load("scene_plan")["scenes"] if s.get("template") == "lineup_board")


def _board_data(spec, dossier=None):
    return _graphic_data(_board(), dossier or fixture("match_dossier"), fixture("prediction"), fixture("match_analysis"), spec)


def _xi(side: str, dossier=None) -> list[dict]:
    return (dossier or fixture("match_dossier"))["facts"][f"{side}.predicted_xi"]["value"]


def test_players_carry_line_and_y_from_the_spec():
    spec = _load("tactic_spec")
    data = _board_data(spec)
    for slot, side in (("home", "H"), ("away", "A")):
        by_number = {p["number"]: p for p in spec["teams"][side]["players"]}
        assert len(data[slot]) == 11
        for got, original in zip(data[slot], _xi(side)):
            assert {k: got[k] for k in original} == original  # name, number and tag are the dossier's
            assert got["line"] == by_number[got["number"]]["line"]
            assert got["y"] == by_number[got["number"]]["pos"][1]  # team-normalized: left side has the small y


def test_the_dossier_is_not_changed():
    dossier = fixture("match_dossier")
    before = copy.deepcopy(dossier)
    data = _board_data(_load("tactic_spec"), dossier)
    assert dossier == before
    assert "line" in data["home"][0] and "line" not in _xi("H", dossier)[0]


def test_no_spec_keeps_the_dossier_list():
    data = _board_data(None)
    assert data["home"] == _xi("H") and data["away"] == _xi("A")


def test_a_spec_without_teams_keeps_the_dossier_list():
    data = _board_data({})
    assert data["home"] == _xi("H")


def test_an_unmatched_player_falls_back_for_that_team_only():
    spec = _load("tactic_spec")
    spec["teams"]["H"]["players"][4]["number"] = 77
    data = _board_data(spec)
    assert data["home"] == _xi("H")
    assert all("line" in p and "y" in p for p in data["away"])


@pytest.mark.parametrize("change", ["missing_number", "text_number", "listed_twice"])
def test_a_player_without_a_unique_number_falls_back(change):
    dossier = fixture("match_dossier")
    xi = _xi("H", dossier)
    if change == "missing_number":
        del xi[3]["number"]
    elif change == "text_number":
        xi[3]["number"] = str(xi[3]["number"])
    else:
        xi[3]["number"] = xi[4]["number"]
    data = _board_data(_load("tactic_spec"), dossier)
    assert data["home"] == xi
    assert all("line" in p for p in data["away"])


def test_a_spec_with_a_repeated_number_falls_back():
    spec = _load("tactic_spec")
    players = spec["teams"]["A"]["players"]
    players[5]["number"] = players[6]["number"]
    data = _board_data(spec)
    assert data["away"] == _xi("A")
    assert all("line" in p for p in data["home"])


def test_other_templates_are_left_alone():
    scene = next(s for s in _load("scene_plan")["scenes"] if s.get("template") == "team_news")
    data = _graphic_data(scene, fixture("match_dossier"), fixture("prediction"), fixture("match_analysis"), _load("tactic_spec"))
    assert all("line" not in p for p in data["home"])


STYLE = {"color": "accent", "dash": True, "fill": False, "curved": True}


@pytest.mark.parametrize("action,colour", [("A9@move#1", "A"), ("H11@carry#2", "H")])
def test_a_run_arrow_takes_the_runners_team(action, colour):
    o = {"id": "S09:N06", "kind": "run_arrow", "style": STYLE}
    scene = {"id": "S09", "overlays": [{"id": "N05", "action": "H2@move#1"}, {"id": "N06", "action": action}]}
    assert _overlay_style(o, scene) == {**STYLE, "color": colour}
    assert STYLE["color"] == "accent"  # the choreography's style is not changed


def test_other_overlays_keep_their_colour():
    o = {"id": "S09:N06", "kind": "pass_line", "style": STYLE}
    assert _overlay_style(o, {"id": "S09", "overlays": [{"id": "N06", "event": "E1"}]}) == STYLE


def test_a_run_arrow_with_no_plan_entry_keeps_its_colour():
    o = {"id": "S09:N06", "kind": "run_arrow", "style": STYLE}
    assert _overlay_style(o, {"id": "S09", "overlays": []}) == STYLE


def test_built_props_are_schema_valid_with_both_changes():
    plan, spec, narration = _load("scene_plan"), _load("tactic_spec"), _load("narration_script")
    brief = fixture("brief.match")
    doc = build_doc(plan, spec, brief, "fx", {})
    props = build(doc, provisional(doc, narration, "fx"), brief, narration, plan, spec, scale=0.5, dossier=fixture("match_dossier"),
                  prediction=fixture("prediction"), analysis=fixture("match_analysis"))
    assert schema.validate_artifact("render_props", props) == []
    arrows = [o for o in props["overlays"] if o["kind"] == "run_arrow"]
    assert arrows and all(o["style"]["color"] == "H" for o in arrows)  # the fixture's only run belongs to H7
    assert {o["style"]["color"] for o in props["overlays"] if o["kind"] == "pass_line"} <= {"ink"}
    board = next(g for g in props["graphics"] if g["template"] == "lineup_board")["data"]
    assert all("line" in p and "y" in p for p in board["home"] + board["away"])


def _collector_dossier():
    """The real collector report (trimmed fixture) mapped and merged into a dossier, the way the research stage does it."""
    raw = json.loads((M / "collector_report.json").read_text(encoding="utf-8"))
    report = CollectionReport.model_validate(raw)
    report.finished_at = datetime(2026, 11, 2, 12, tzinfo=UTC)
    brief = fixture("brief.match")
    brief["match"].update(home="Newcastle", away="Everton", kickoff_utc="2026-11-02T20:00:00Z")
    return merge("fx", brief, [], None, "2026-11-02T13:00:00Z", {"brief": "0" * 64, "collector_claims": "1" * 64}, 0, map_report(report, brief)["claims"])


@pytest.mark.parametrize("key,played", [("H.split.overall", 8), ("A.split.overall", 8), ("H.split.home", 4), ("A.split.away", 4)])
def test_a_split_key_resolves_to_the_whole_record(key, played):
    record = resolve_ref(key, _collector_dossier(), None)
    assert record["played"] == played and record["ht_ft_sample"] == played
    assert {"wdl", "goals_for", "goals_against", "btts", "goal_lines", "ht_ft"} <= set(record)
    assert set(record["ht_ft"]) >= {"W/W", "W/D", "W/L", "L/W"} and "over" in record["goal_lines"]["2.5"]


def test_pattern_compare_data_carries_both_records_and_the_title():
    dossier = _collector_dossier()
    scene = {"template": "pattern_compare", "bind": {"title": "text:League patterns", "home": "H.split.overall", "away": "A.split.overall"}}
    assert _graphic_data(scene, dossier, None) == {"title": "League patterns", "home": resolve_ref("H.split.overall", dossier, None),
                                                   "away": resolve_ref("A.split.overall", dossier, None)}


def test_text_card_bullets_bound_to_string_facts_stay_a_list_of_strings():
    facts = {"H.tactics.press": {"value": "Press high from the front."}, "A.tactics.block": {"value": "Sit in a mid-block."}}
    scene = {"template": "text_card", "bind": {"headline": "text:The plan", "bullets": ["H.tactics.press", "text:Then counter", "A.tactics.block"]}}
    assert _graphic_data(scene, {"facts": facts}, None)["bullets"] == ["Press high from the front.", "Then counter", "Sit in a mid-block."]


def _built_with_brief(brief, **kw):
    plan, spec, narration = _load("scene_plan"), _load("tactic_spec"), _load("narration_script")
    doc = build_doc(plan, spec, brief, "fx", {})
    return build(doc, provisional(doc, narration, "fx"), brief, narration, plan, spec, scale=0.5, dossier=fixture("match_dossier"),
                 prediction=fixture("prediction"), analysis=fixture("match_analysis"), **kw)


def test_crests_reach_the_props_only_when_switched_on(tmp_path):
    (tmp_path / "c.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="8" height="8"/></svg>')
    brief = fixture("brief.match")
    off = _built_with_brief(brief)
    brief["teams"]["H"]["crest"] = brief["teams"]["A"]["crest"] = "c.svg"
    assert _built_with_brief(brief, project_dir=tmp_path)["theme"] == off["theme"]  # named, but not switched on
    brief["show_crests"] = True
    on = _built_with_brief(brief, project_dir=tmp_path)
    assert schema.validate_artifact("render_props", on) == []
    assert all(t["crest"].startswith("data:image/svg+xml;base64,") for t in on["theme"]["teams"].values())
    for t in on["theme"]["teams"].values():
        del t["crest"]
    assert on == off  # the crests are the only difference


def test_show_crests_without_a_project_folder_is_an_error_not_a_silent_drop():
    brief = fixture("brief.match")
    brief["show_crests"] = True
    with pytest.raises(ValueError, match="project folder"):
        _built_with_brief(brief)


def test_the_tactic_still_never_carries_crests():
    brief = fixture("brief")
    brief.update(show_crests=True)  # no project folder and no crest files: the still does not look for them
    assert all("crest" not in t for t in still_props(fixture("tactic_spec"), brief)["theme"]["teams"].values())


# --- team_news order and stat_compare rank rows --------------------------------------------------------------------

def _news_scene():
    return {"template": "team_news", "bind": {"home": ["H.injuries", "H.suspensions"], "away": ["A.injuries", "A.suspensions"]}}


def _news_dossier(home_injuries, home_bans):
    return {"facts": {"H.injuries": {"value": home_injuries}, "H.suspensions": {"value": home_bans},
                      "A.injuries": {"value": []}, "A.suspensions": {"value": []}}}


def test_team_news_lists_bans_then_outs_then_doubts():
    injuries = [{"player": "Out1", "reason": "knee", "status": "out"}, {"player": "Doubt1", "reason": "hip", "status": "doubt"},
                {"player": "Out2", "reason": "shin", "status": "out"}, {"player": "Odd", "reason": "?"},
                {"player": "Doubt2", "reason": "calf", "status": "doubt"}, {"player": "Out3", "reason": "ankle", "status": "out"}]
    bans = [{"player": "Banned", "reason": "red card", "status": "out"}]
    data = _graphic_data(_news_scene(), _news_dossier(injuries, bans), None)
    assert [p["player"] for p in data["home"]] == ["Banned", "Out1", "Out2", "Out3", "Doubt1", "Doubt2", "Odd"]
    assert data["away"] == []


def test_team_news_a_ban_without_a_status_counts_as_out_and_nothing_is_changed():
    injuries = [{"player": "Out1", "reason": "knee", "status": "out"}, {"player": "Doubt1", "reason": "hip", "status": "doubt"}]
    bans = [{"player": "Banned", "reason": "ban"}]
    dossier = _news_dossier(injuries, bans)
    before = copy.deepcopy(dossier)
    data = _graphic_data(_news_scene(), dossier, None)
    assert [p["player"] for p in data["home"]] == ["Banned", "Out1", "Doubt1"]
    assert dossier == before and data["home"][0] == {"player": "Banned", "reason": "ban"}  # order only, no invented status


def test_team_news_on_the_fixture_shows_every_out_before_any_doubt():
    scene = next(s for s in _load("scene_plan")["scenes"] if s.get("template") == "team_news")
    data = _graphic_data(scene, fixture("match_dossier"), fixture("prediction"))
    for side in ("home", "away"):
        st = [p.get("status") for p in data[side]]
        assert st == sorted(st, key=lambda s: {"out": 0, "doubt": 1}.get(s, 2))


def _stat_facts():
    return {"facts": {f"{t}.{k}": {"value": v} for t, vals in (("H", (17, 7, 1.1)), ("A", (10, 12, 1.2)))
                      for k, v in zip(("standing.position", "standing.points", "goals_for_avg"), vals)}}


def test_stat_compare_flags_rank_rows_as_lower_is_better():
    scene = {"template": "stat_compare", "bind": {
        "labels": ["text:League position", "text:Points", "text:Goals"],
        "home": ["H.standing.position", "H.standing.points", "H.goals_for_avg"],
        "away": ["A.standing.position", "A.standing.points", "A.goals_for_avg"]}}
    data = _graphic_data(scene, _stat_facts(), None)
    assert data["home"] == [17, 7, 1.1] and data["away"] == [10, 12, 1.2]
    assert data["lower_better"] == [True, False, False]


def test_stat_compare_without_rank_rows_carries_no_flag():
    scene = {"template": "stat_compare", "bind": {"labels": ["text:Points"], "home": ["H.standing.points"], "away": ["A.standing.points"]}}
    assert "lower_better" not in _graphic_data(scene, _stat_facts(), None)


def test_built_stat_compare_with_a_rank_row_is_schema_valid():
    plan, spec, narration = _load("scene_plan"), _load("tactic_spec"), _load("narration_script")
    scene = next(s for s in plan["scenes"] if s.get("template") == "stat_compare")
    scene["bind"]["home"][0] = "H.standing.position"
    scene["bind"]["away"][0] = "A.standing.position"
    dossier = fixture("match_dossier")
    for t, v in (("H", 3), ("A", 9)):
        dossier["facts"].setdefault(f"{t}.standing.position", {"value": v})
    brief = fixture("brief.match")
    doc = build_doc(plan, spec, brief, "fx", {})
    props = build(doc, provisional(doc, narration, "fx"), brief, narration, plan, spec, scale=0.5, dossier=dossier,
                  prediction=fixture("prediction"), analysis=fixture("match_analysis"))
    assert schema.validate_artifact("render_props", props) == []
    g = next(g for g in props["graphics"] if g["template"] == "stat_compare")["data"]
    assert g["lower_better"][0] is True and not any(g["lower_better"][1:])


@pytest.mark.parametrize("order", ["battle_first", "title_first"])
def test_a_text_title_and_why_override_the_key_battle_in_any_bind_order(order):
    analysis = {"key_battles": [{"id": "KB1", "title": "Battle title", "why": "Battle why",
                                 "home_player": "H4", "away_player": "A9"}]}
    spec = {"teams": {"H": {"players": [{"id": "H4", "name": "Home Four", "number": 4}]},
                      "A": {"players": [{"id": "A9", "name": "Away Nine", "number": 9}]}}}
    over = {"title": "text:Short title", "why": "text:Short why"}
    bind = {"battle": "KB1", **over} if order == "battle_first" else {**over, "battle": "KB1"}
    d = _graphic_data({"template": "key_player_duel", "bind": bind}, None, None, analysis, spec)
    assert (d["title"], d["why"]) == ("Short title", "Short why")
    assert d["home_player"] == {"name": "Home Four", "number": 4}
    plain = _graphic_data({"template": "key_player_duel", "bind": {"battle": "KB1"}}, None, None, analysis, spec)
    assert (plain["title"], plain["why"]) == ("Battle title", "Battle why")
