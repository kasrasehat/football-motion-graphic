"""Engine side of the graphics (no rendering): the line-up board's rows come from the tactic spec by shirt number, run
arrows take the running player's team colour. The renderer's half is in render/test/graphics.test.ts."""
from __future__ import annotations

import copy
import json

import pytest

from tests.helpers import FIX, fixture
from tms import schema
from tms.choreo.document import build_doc
from tms.props.builder import _graphic_data, _overlay_style, build
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
