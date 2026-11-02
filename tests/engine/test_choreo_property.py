"""Property test: random legal storyboards compile to finite tracks that satisfy the ball/possession rules."""
from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tms.choreo.document import build_doc
from tms.validate import validate_doc
from tms.validate.registry import Context
from tests.helpers import fixture

SPEC = fixture("tactic_spec")
BRIEF = fixture("brief")
H_OUT = [f"H{i}" for i in range(2, 12)]
A_ALL = [f"A{i}" for i in range(1, 12)]
BALL_RULES = {"CH-20", "CH-21", "CH-23", "CH-24", "CH-25"}


@st.composite
def plans(draw):
    holder = SPEC["ball"]["holder"]
    actions = []
    n_pass = draw(st.integers(1, 4))
    for k in range(n_pass):
        to = draw(st.sampled_from([p for p in H_OUT if p != holder]))
        at = round(draw(st.floats(0.2, 1.0)), 2) if k == 0 else {"after": f"E{k:02d}", "plus": round(draw(st.floats(0.4, 1.5)), 2)}
        actions.append({"type": "pass", "id": f"E{k + 1:02d}", "from": holder, "to": to, "at": at,
                        "kind": draw(st.sampled_from(["ground", "driven", "lofted"]))})
        holder = to
    movers = draw(st.lists(st.sampled_from(H_OUT + A_ALL[1:]), min_size=0, max_size=4, unique=True))
    for pid in movers:
        actions.append({"type": "move", "player": pid, "at": round(draw(st.floats(0.0, 4.0)), 2),
                        "to": {"pitch": [draw(st.floats(15, 90)), draw(st.floats(6, 62))]},
                        "pace": draw(st.sampled_from(["jog", "run", "sprint"])), "curve_m": draw(st.floats(-5, 5))})
    if draw(st.booleans()):
        actions.append({"type": "press", "player": "A9", "on": SPEC["ball"]["holder"], "at": 0.3, "pace": "sprint", "until": 2.0})
    scene = {"id": "S01", "kind": "pitch", "purpose": "demonstrate", "title": "Random", "principles": ["P1"],
             "transition": "continue", "reset_to": None, "length_s": None, "shape": [], "actions": actions,
             "holds": [], "overlays": [], "camera": [{"at": 0, "mode": "follow", "target": "ball", "w_m": 70}]}
    outro = {"id": "S02", "kind": "graphic", "purpose": "outro", "title": "End", "transition": "cut", "length_s": 2,
             "template": "text_card", "bind": {"headline": "text:End"}, "reveals": []}
    return {"version": "1", "project_id": "fx-ifb-442", "start": {"from": "tactic_snapshot", "overrides": {}},
            "scenes": [scene, outro]}


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(plans())
def test_random_storyboards_respect_ball_rules(plan):
    doc = build_doc(plan, SPEC, BRIEF, "fx-ifb-442", {})
    for arr in list(doc["tracks"]["players"].values()) + [doc["tracks"]["ball"], doc["camera_track"]]:
        assert all(isinstance(v, int) and not math.isnan(v) for v in arr)
    fs = validate_doc("choreography", doc, Context(mode="tactic", artifacts={"scene_plan": plan, "tactic_spec": SPEC, "brief": BRIEF}))
    bad = [(f.rule, f.message) for f in fs if f.severity == "error" and f.rule in BALL_RULES | {"SCHEMA"}]
    assert not bad, bad
