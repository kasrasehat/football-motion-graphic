"""GS rules on the match-preview storyboard fixture."""
from __future__ import annotations

import json

import pytest

from tms.validate.registry import Context
from tests.helpers import FIX, expect_clean, expect_violation, fixture

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
