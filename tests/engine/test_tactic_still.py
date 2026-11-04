"""The expected-shapes still's props: titles beside the pitch, whole pitch in view, ball clear of the holder."""
from __future__ import annotations

import json

import pytest

from tests.helpers import FIX
from tests.render.gen_still_fixtures import ASPECTS, STILL, dense_props
from tms import schema
from tms.render import projection as P
from tms.tactic.still import name_label, still_props

pytestmark = pytest.mark.fast

ORIENTATIONS = tuple(ASPECTS)


def _spec() -> dict:
    return json.loads((STILL / "tactic_spec.json").read_text(encoding="utf-8"))


def _pitch_box(props: dict) -> tuple[float, float, float, float]:
    """Screen box of the pitch with its goals (2 m behind each goal line)."""
    cam = P.camera_at(props, 0)
    a = P.world_to_screen(-2, 0, cam, props["width"], props["height"], props["orientation"])
    b = P.world_to_screen(107, 68, cam, props["width"], props["height"], props["orientation"])
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


@pytest.mark.parametrize("orientation", ORIENTATIONS)
def test_generated_fixture_is_current(orientation):
    on_disk = json.loads((STILL / f"props.{orientation}.json").read_text(encoding="utf-8"))
    assert on_disk == dense_props(orientation), "run: .venv/Scripts/python.exe tests/render/gen_still_fixtures.py"


@pytest.mark.parametrize("orientation", ORIENTATIONS)
@pytest.mark.parametrize("scale", [1.0, 0.5])
def test_schema_valid(orientation, scale):
    assert schema.validate_artifact("render_props", dense_props(orientation, scale)) == []


@pytest.mark.parametrize("orientation", ORIENTATIONS)
@pytest.mark.parametrize("scale", [1.0, 0.5])
def test_pitch_is_whole_and_clear_of_the_panel(orientation, scale):
    props = dense_props(orientation, scale)
    x0, y0, x1, y1 = _pitch_box(props)
    assert x0 >= 0 and y0 >= 0 and x1 <= props["width"] and y1 <= props["height"]
    rx0, ry0, rx1, ry1 = props["principleRail"]["rect"]
    assert 0 <= rx0 < rx1 <= props["width"] and 0 <= ry0 < ry1 <= props["height"]
    assert x1 <= rx0 or y1 <= ry0, f"pitch {x0, y0, x1, y1} runs under the panel {rx0, ry0, rx1, ry1}"


def test_no_title_is_written_on_the_pitch():
    props = dense_props("landscape")
    assert not [o for o in props["overlays"] if o["kind"] == "label" or o["label"]]
    assert props["scenes"][0]["title"] == ""  # a one-frame lower-third would only be a smear at frame 0


def test_panel_holds_whole_titles_and_every_involved_player():
    spec = _spec()
    rail = dense_props("landscape")["principleRail"]
    assert rail["title"] == spec["title"]
    assert [p["id"] for p in rail["principles"]] == [p["id"] for p in spec["principles"]]
    assert [p["name"] for p in rail["principles"]] == [p["name"] for p in spec["principles"]]
    numbers = {p["id"]: (t, p["number"]) for t in "HA" for p in spec["teams"][t]["players"]}
    for got, want in zip(rail["principles"], spec["principles"]):
        assert sorted((c["team"], c["number"]) for c in got["players"]) == sorted(numbers[pid] for pid in want["players"])
        teams = [c["team"] for c in got["players"]]
        assert teams == sorted(teams, key="HA".index), "home players listed first"


def test_panel_names_the_ball_holder():
    rail = dense_props("landscape")["principleRail"]
    assert rail["ball"] == {"team": "A", "number": 20, "name": "Bernardo Silva"}


def test_rings_cover_each_involved_player_once():
    spec = _spec()
    props = dense_props("landscape")
    rings = [o for o in props["overlays"] if o["kind"] == "ring"]
    assert len(rings) == 1
    pts = rings[0]["geom"]["static"]
    assert len(pts) == len({tuple(p) for p in pts}) == len({pid for pr in spec["principles"] for pid in pr["players"]})


@pytest.mark.parametrize("orientation", ORIENTATIONS)
def test_ball_clear_of_holder_ring_and_every_other_token(orientation):
    props = dense_props(orientation)
    w, h, o = props["width"], props["height"], props["orientation"]
    cam = P.camera_at(props, 0)
    s = P.px_per_metre(cam[2], w, h, o)
    u = P.resolution_factor(w, h)
    ring = P.ring_outer_radius_px(P.token_radius_px(cam[2], w, h, o), u)
    ball = P.project_ball(props, 0)
    gap = min(((P.project_player(props, e["id"], 0)[0] - ball[0]) ** 2 + (P.project_player(props, e["id"], 0)[1] - ball[1]) ** 2) ** 0.5
              for e in props["entities"])
    assert gap >= ring + P.ball_radius_px(s, u)


def test_ball_stays_on_the_pitch_for_a_holder_on_the_line():
    spec = _spec()
    spec["ball"]["holder"] = "H2"
    holder = next(p for p in spec["teams"]["H"]["players"] if p["id"] == "H2")
    holder["pos"] = [104.5, 67.5]
    brief = json.loads((STILL / "brief.json").read_text(encoding="utf-8"))
    x, y, _z = P.ball_at(still_props(spec, brief), 0)
    assert 0 <= x <= 105 and 0 <= y <= 68


def test_show_names_off_means_no_names_anywhere():
    brief = json.loads((STILL / "brief.json").read_text(encoding="utf-8"))
    props = still_props(_spec(), {**brief, "show_names": False})
    assert all(e["label"] is None for e in props["entities"])
    assert props["principleRail"]["ball"]["name"] is None
    assert schema.validate_artifact("render_props", props) == []


def test_long_names_are_shortened_at_a_word_and_stay_schema_valid():
    assert name_label("Bernardo Silva") == "Bernardo Silva"
    assert name_label("Maximiliano Bartholomew Fitzgerald") == "Fitzgerald"
    assert name_label("Pierre-Emerick Emiliano Aubameyang") == "Aubameyang"
    assert name_label("Abcdefghijklmnopqrstuvwxyz") == "Abcdefghijklmnopq…"
    assert name_label("") is None
    assert name_label(None) is None
    spec = _spec()
    spec["teams"]["H"]["players"][0]["name"] = "Maximiliano Bartholomew Fitzgerald"
    brief = json.loads((STILL / "brief.json").read_text(encoding="utf-8"))
    assert schema.validate_artifact("render_props", still_props(spec, brief)) == []


def test_fixture_spec_and_brief_are_valid_and_really_dense():
    assert schema.validate_artifact("tactic_spec", _spec()) == []
    assert schema.validate_artifact("brief", json.loads((STILL / "brief.json").read_text(encoding="utf-8"))) == []
    props = dense_props("landscape")
    ids = [e["id"] for e in props["entities"]]
    near = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]
            if ((P.player_at(props, a, 0)[0] - P.player_at(props, b, 0)[0]) ** 2
                + (P.player_at(props, a, 0)[1] - P.player_at(props, b, 0)[1]) ** 2) ** 0.5 < 6]
    assert len(near) >= 4, near
    assert FIX in STILL.parents
