"""GS rules on the match-preview storyboard fixture."""
from __future__ import annotations

import json

import pytest

from tms.validate.registry import Context
from tests.helpers import FIX, expect_clean, expect_violation, findings, fixture

pytestmark = pytest.mark.fast
M = FIX / "match"


def plan():
    return json.loads((M / "scene_plan.json").read_text(encoding="utf-8"))


def ctx(mode="match_preview"):
    spec = json.loads((M / "tactic_spec.json").read_text(encoding="utf-8"))
    return Context(mode=mode, artifacts={"brief": fixture("brief.match"), "tactic_spec": spec, "match_dossier": fixture("match_dossier"),
                                         "prediction": fixture("prediction"), "match_analysis": fixture("match_analysis")})


def scene(p, sid):
    return next(s for s in p["scenes"] if s["id"] == sid)


def test_fixture_clean():
    expect_clean("scene_plan", plan(), ctx())


def test_GS01_missing_slot():
    p = plan()
    del scene(p, "S09")["bind"]["draw"]
    expect_violation("GS-01", "scene_plan", p, ctx())


def test_GS02_unresolvable_ref():
    p = plan()
    scene(p, "S02")["bind"]["home"] = "H.form.last10"
    expect_violation("GS-02", "scene_plan", p, ctx())


def test_GS03_wrong_shape():
    p = plan()
    scene(p, "S09")["bind"]["home"] = "H.goals_for_avg"  # 2.3 is not a probability
    expect_violation("GS-03", "scene_plan", p, ctx())


def test_GS04_data_graphic_in_tactic_mode():
    p = fixture("scene_plan")
    s = scene(p, "S06")
    s.update(template="form_guide", bind={"home": "H.form.last5", "away": "A.form.last5"})
    expect_violation("GS-04", "scene_plan", p, Context(mode="tactic", artifacts={"tactic_spec": fixture("tactic_spec")}))


def test_GS05_reveal_too_late():
    p = plan()
    scene(p, "S03")["reveals"][-1]["at"] = 7.5
    expect_violation("GS-05", "scene_plan", p, ctx())


def test_GS06_preview_without_prediction():
    p = plan()
    p["scenes"] = [s for s in p["scenes"] if s["template" if s["kind"] == "graphic" else "kind"] not in ("probability_bar", "prediction_card")]
    expect_violation("GS-06", "scene_plan", p, ctx())


def test_GS07_typed_number():
    p = plan()
    scene(p, "S10")["bind"]["note"] = "text:Madrid win 2-1 for sure, 70 percent"
    expect_violation("GS-07", "scene_plan", p, ctx())


SPLIT = {"played": 8, "btts": {"yes": 4, "no": 4}, "goal_lines": {"2.5": {"over": 3, "under": 5}}, "ht_ft_sample": 8, "ht_ft": {"W/W": 1}}


def pattern_scene(home="H.split.overall", away="A.split.overall"):
    return {**scene(plan(), "S09"), "id": "S20", "template": "pattern_compare", "bind": {"home": home, "away": away}}


def pattern_ctx():
    c = ctx()
    dossier = json.loads(json.dumps(c.artifacts["match_dossier"]))
    dossier["facts"]["H.split.overall"] = {"value": SPLIT}
    dossier["facts"]["A.split.overall"] = {"value": SPLIT}
    dossier["facts"]["A.tactics.note"] = {"value": "A text fact"}
    c.artifacts["match_dossier"] = dossier
    return c


def test_pattern_compare_binds_two_split_records():
    p = plan()
    p["scenes"].append(pattern_scene())
    fs = findings("scene_plan", p, pattern_ctx())
    assert not [f for f in fs if f.severity == "error"], [(f.rule, f.message) for f in fs]


def test_GS01_pattern_compare_missing_slot():
    p = plan()
    s = pattern_scene()
    del s["bind"]["away"]
    p["scenes"].append(s)
    expect_violation("GS-01", "scene_plan", p, pattern_ctx())


@pytest.mark.parametrize("away", ["A.tactics.note", "text:No data", ["A.split.overall"]])
def test_GS03_pattern_compare_slot_is_not_a_record(away):
    p = plan()
    p["scenes"].append(pattern_scene(away=away))
    expect_violation("GS-03", "scene_plan", p, pattern_ctx())


def test_GS04_pattern_compare_needs_match_data():
    p = plan()
    p["scenes"].append(pattern_scene())
    expect_violation("GS-04", "scene_plan", p, Context(mode="tactic", artifacts={"tactic_spec": fixture("tactic_spec")}))


def text_card(bullets):
    return {**scene(plan(), "S09"), "id": "S20", "template": "text_card", "bind": {"headline": "text:The plan", "bullets": bullets}}


def test_text_card_bullets_from_string_facts_are_clean():
    p = plan()
    p["scenes"].append(text_card(["A.tactics.note", "text:Then counter"]))
    assert not [f for f in findings("scene_plan", p, pattern_ctx()) if f.severity == "error"]


@pytest.mark.parametrize("bullets", [["A.tactics.note", "H.goals_for_avg"], "A.tactics.note", ["H.split.overall"]])
def test_GS03_text_card_bullet_is_not_a_string(bullets):
    p = plan()
    p["scenes"].append(text_card(bullets))
    expect_violation("GS-03", "scene_plan", p, pattern_ctx())
