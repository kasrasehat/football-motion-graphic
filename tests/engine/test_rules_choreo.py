"""CH + NS rules: the compiled fixture storyboard is clean; each mutation triggers its rule."""
from __future__ import annotations

import copy

import pytest

from tms.choreo.document import build_doc
from tms.validate.registry import Context
from tests.helpers import expect_clean, expect_violation, fixture

pytestmark = pytest.mark.fast
FPS = 30


@pytest.fixture(scope="module")
def compiled():
    return build_doc(fixture("scene_plan"), fixture("tactic_spec"), fixture("brief"), "fx-ifb-442", {})


def ctx(plan=None, doc=None, brief=None, mode="tactic", **extra):
    arts = {"scene_plan": plan or fixture("scene_plan"), "tactic_spec": fixture("tactic_spec"), "brief": brief or fixture("brief")}
    if doc is not None:
        arts["choreography"] = doc
    arts.update(extra)
    return Context(mode=mode, artifacts=arts)


def recompile(plan):
    return build_doc(plan, fixture("tactic_spec"), fixture("brief"), "fx-ifb-442", {})


def setpos(doc, pid, f, x, y):
    doc["tracks"]["players"][pid][2 * f:2 * f + 2] = [round(x * 100), round(y * 100)]


def getpos(doc, pid, f):
    a = doc["tracks"]["players"][pid]
    return a[2 * f] / 100, a[2 * f + 1] / 100


def scene(plan, sid):
    return next(s for s in plan["scenes"] if s["id"] == sid)


def test_compiled_fixture_has_no_errors(compiled):
    expect_clean("choreography", compiled, ctx())


# ------------------------------------------------------------------ structure
def test_CH01_scene_too_long(compiled):
    d = copy.deepcopy(compiled)
    d["scenes"][1]["len"] = 25.0
    expect_violation("CH-01", "choreography", d, ctx())


def test_CH02_unresolvable_reference():
    plan = fixture("scene_plan")
    scene(plan, "S03")["actions"][3]["at"] = {"after": "E99", "plus": 0.2}
    expect_violation("CH-02", "choreography", recompile(plan), ctx(plan))


def test_CH03_principle_never_shown(compiled):
    plan = fixture("scene_plan")
    for s in plan["scenes"]:
        if s["kind"] == "pitch":
            s["principles"] = [p for p in s["principles"] if p != "P3"]
    expect_violation("CH-03", "choreography", compiled, ctx(plan))


def test_CH04_large_override(compiled):
    expect_violation("CH-04", "choreography", compiled, ctx())  # the fixture moves H2 22 m (a warning by design)


def test_CH05_static_scene(compiled):
    plan = fixture("scene_plan")
    scene(plan, "S01")["overlays"] = []
    expect_violation("CH-05", "choreography", compiled, ctx(plan))


# ------------------------------------------------------------------ players
def test_CH10_too_fast(compiled):
    d = copy.deepcopy(compiled)
    x, y = getpos(d, "H5", 100)
    for i in range(30):
        setpos(d, "H5", 100 + i, x + 0.4 * i, y)  # 12 m/s
    expect_violation("CH-10", "choreography", d, ctx())


def test_CH11_long_sprint(compiled):
    d = copy.deepcopy(compiled)
    for i in range(160):
        setpos(d, "A3", 40 + i, 20 + 0.27 * i, 60)  # 8.1 m/s for 5.3 s
    expect_violation("CH-11", "choreography", d, ctx())


def test_CH12_impossible_turn(compiled):
    d = copy.deepcopy(compiled)
    x, y = getpos(d, "H5", 200)
    for i in range(20):
        setpos(d, "H5", 200 + i, x + 0.2 * i, y)
    for i in range(20):
        setpos(d, "H5", 220 + i, x + 4.0 - 0.2 * i, y)
    expect_violation("CH-12", "choreography", d, ctx())


def test_CH13_teleport(compiled):
    d = copy.deepcopy(compiled)
    x, y = getpos(d, "H5", 250)
    for f in range(250, 260):
        setpos(d, "H5", f, x + 3, y)
    expect_violation("CH-13", "choreography", d, ctx())


def test_CH14_off_pitch(compiled):
    d = copy.deepcopy(compiled)
    for f in range(100, 110):
        x, _ = getpos(d, "H3", f)
        setpos(d, "H3", f, x, -5)
    expect_violation("CH-14", "choreography", d, ctx())


def test_CH15_teammates_collide(compiled):
    d = copy.deepcopy(compiled)
    for f in range(100, 120):
        setpos(d, "H5", f, *getpos(d, "H4", f))
    expect_violation("CH-15", "choreography", d, ctx())


def test_CH16_dead_shape(compiled):
    d = copy.deepcopy(compiled)
    fl = next(p for p in d["possession"] if p["state"] == "flight")
    fl["tau1"] = fl["tau0"] + 3.0
    a = int(fl["tau0"] * FPS)
    for pid in d["tracks"]["players"]:
        x, y = getpos(d, pid, a)
        for f in range(a, a + 90):
            setpos(d, pid, f, x, y)
    expect_violation("CH-16", "choreography", d, ctx())


# ------------------------------------------------------------------ ball
def test_CH20_possession_gap(compiled):
    d = copy.deepcopy(compiled)
    del d["possession"][3]
    expect_violation("CH-20", "choreography", d, ctx())


def test_CH21_ball_away_from_carrier(compiled):
    d = copy.deepcopy(compiled)
    for f in range(30, 40):
        d["tracks"]["ball"][3 * f] += 300
    expect_violation("CH-21", "choreography", d, ctx())


def test_CH22_pass_too_fast(compiled):
    d = copy.deepcopy(compiled)
    e = next(x for x in d["events"] if x["type"] == "pass")
    e["tau1"] = e["tau0"] + 0.3
    expect_violation("CH-22", "choreography", d, ctx())


def test_CH23_pass_not_from_passer(compiled):
    d = copy.deepcopy(compiled)
    e = next(x for x in d["events"] if x["type"] == "pass")
    e["p0"] = [e["p0"][0] + 4, e["p0"][1]]
    expect_violation("CH-23", "choreography", d, ctx())


def test_CH24_pass_too_short(compiled):
    d = copy.deepcopy(compiled)
    e = next(x for x in d["events"] if x["type"] == "pass")
    e["p1"] = [e["p0"][0] + 2, e["p0"][1]]
    expect_violation("CH-24", "choreography", d, ctx())


def test_CH25_pass_by_non_holder():
    plan = fixture("scene_plan")
    scene(plan, "S03")["actions"][3]["from"] = "H8"
    expect_violation("CH-25", "choreography", recompile(plan), ctx(plan))


def test_CH26_impossible_interception():
    plan = fixture("scene_plan")
    scene(plan, "S03")["actions"].append({"type": "intercept", "id": "E09", "by": "A1", "pass": "E02"})
    expect_violation("CH-26", "choreography", recompile(plan), ctx(plan))


def test_CH27_ball_off_pitch(compiled):
    d = copy.deepcopy(compiled)
    for f in range(300, 310):
        d["tracks"]["ball"][3 * f + 1] = -800
    expect_violation("CH-27", "choreography", d, ctx())


def test_CH30_offside_receiver(compiled):
    d = copy.deepcopy(compiled)
    e = next(x for x in d["events"] if x["id"] == "S04:E03")
    f = int(round(e["tau0"] * FPS))
    setpos(d, "H9", f, 92, 34)
    expect_violation("CH-30", "choreography", d, ctx())


# ------------------------------------------------------------------ overlays
def test_CH40_overlay_flash(compiled):
    d = copy.deepcopy(compiled)
    o = d["overlays"][0]
    o["tau_out"] = o["tau_in"] + 0.5
    expect_violation("CH-40", "choreography", d, ctx())


def test_CH41_label_too_short_to_read(compiled):
    d = copy.deepcopy(compiled)
    o = next(x for x in d["overlays"] if x["label"])
    o["tau_out"] = o["tau_in"] + 1.0
    expect_violation("CH-41", "choreography", d, ctx())


def test_CH42_clutter(compiled):
    d = copy.deepcopy(compiled)
    base = d["overlays"][0]
    for i in range(5):
        d["overlays"].append(dict(base, id=f"X:{i}", label=None))
    expect_violation("CH-42", "choreography", d, ctx())


def test_CH43_arrow_after_run(compiled):
    d = copy.deepcopy(compiled)
    o = next(x for x in d["overlays"] if x["id"] == "S02:N03")
    a = next(x for x in d["actions"] if x["handle"] == "S02:H2@move#1")
    o["tau_in"] = a["tau0"] + 0.1
    expect_violation("CH-43", "choreography", d, ctx())


def test_CH44_tiny_zone(compiled):
    d = copy.deepcopy(compiled)
    z = next(x for x in d["overlays"] if x["kind"] == "zone")
    z["geom"] = {"static": [[50, 30], [51, 30], [51, 31], [50, 31]]}
    expect_violation("CH-44", "choreography", d, ctx())


# ------------------------------------------------------------------ camera
def test_CH50_zoomed_too_close(compiled):
    d = copy.deepcopy(compiled)
    d["camera_track"][3 * 100 + 2] = 2000
    expect_violation("CH-50", "choreography", d, ctx())


def test_CH51_whip_pan(compiled):
    d = copy.deepcopy(compiled)
    for i, f in enumerate(range(200, 212)):
        d["camera_track"][3 * f] += 150 * i
    expect_violation("CH-51", "choreography", d, ctx())


def test_CH52_ball_off_screen(compiled):
    d = copy.deepcopy(compiled)
    for f in range(300, 330):
        d["camera_track"][3 * f:3 * f + 3] = [9000, 1000, 3200]
    expect_violation("CH-52", "choreography", d, ctx())


def test_CH53_camera_jump(compiled):
    d = copy.deepcopy(compiled)
    for f in range(250, len(d["camera_track"]) // 3):
        d["camera_track"][3 * f + 1] += 500
    expect_violation("CH-53", "choreography", d, ctx())


# ------------------------------------------------------------------ pacing
def test_CH60_dead_air(compiled):
    d = copy.deepcopy(compiled)
    s = next(x for x in d["scenes"] if x["id"] == "S05")
    s["len"] = 15.0
    expect_violation("CH-60", "choreography", d, ctx())


def test_CH61_too_short_for_target(compiled):
    b = fixture("brief")
    b["target_duration_s"] = 110
    expect_violation("CH-61", "choreography", compiled, ctx(brief=b))


# ================================================================== NS
@pytest.fixture(scope="module")
def nctx(compiled):
    return ctx(doc=compiled)


def ns():
    return fixture("narration_script")


def line(d, sid):
    return next(ln for ln in d["lines"] if ln["scene"] == sid)


def test_narration_fixture_clean(nctx):
    expect_clean("narration_script", ns(), nctx)


def test_NS01_missing_line(nctx):
    d = ns()
    del d["lines"][2]
    expect_violation("NS-01", "narration_script", d, nctx)


def test_NS02_raw_id(nctx):
    d = ns()
    line(d, "S02")["text"] = "H2 leaves the touchline and steps inside, next to the holding midfielder."
    expect_violation("NS-02", "narration_script", d, nctx)


def test_NS03_too_much_speech_for_scene(nctx):
    d = ns()
    line(d, "S06")["text"] = " ".join(["Control the middle and the block has nowhere to hide."] * 4)
    expect_violation("NS-03", "narration_script", d, nctx)


def test_NS04_long_hook(nctx):
    d = ns()
    line(d, "S01")["text"] = "In this video we are going to look in a lot of detail at how one single full-back can break a block."
    expect_violation("NS-04", "narration_script", d, nctx)


def test_NS05_run_on_sentence(nctx):
    d = ns()
    line(d, "S05")["text"] = ("Three at the back and two in the pivot and five in attack and the whole shape rotates "
                              "around a simple full-back movement that anyone can copy on Sunday.")
    expect_violation("NS-05", "narration_script", d, nctx)


def test_NS06_anchor_word_missing(nctx):
    d = ns()
    line(d, "S02")["anchors"][0]["word"] = "sprints"
    expect_violation("NS-06", "narration_script", d, nctx)


def test_NS06_anchor_ref_missing(nctx):
    d = ns()
    line(d, "S03")["anchors"][0]["ref"] = "E07"
    expect_violation("NS-06", "narration_script", d, nctx)


def test_NS07_unused_pronunciation(nctx):
    d = ns()
    d["pronunciations"] = {"Gvardiol": "Gvar-dee-ol"}
    expect_violation("NS-07", "narration_script", d, nctx)


def test_NS08_digit_formation(nctx):
    d = ns()
    line(d, "S05")["text"] = "That is the 3-2-5, built from a simple full-back rotation, with three at the back."
    expect_violation("NS-08", "narration_script", d, nctx)


def test_NS09_filler(nctx):
    d = ns()
    line(d, "S06")["text"] = "Basically, control the middle and the block has nowhere to hide."
    expect_violation("NS-09", "narration_script", d, nctx)


def test_NS10_unbound_and_wrong_numbers(compiled):
    c = ctx(doc=compiled, mode="match_preview", match_dossier=fixture("match_dossier"), prediction=fixture("prediction"))
    d = ns()
    line(d, "S01")["text"] = "Madrid score 2.3 goals a game and win 47% of the time in this model."
    expect_violation("NS-10", "narration_script", d, c)
    line(d, "S01")["numbers"] = [{"text": "2.3", "ref": "H.goals_for_avg"}, {"text": "47%", "ref": "prediction.probs_final.home"}]
    assert "NS-10" not in {f.rule for f in __import__("tests.helpers", fromlist=["findings"]).findings("narration_script", d, c)}
    line(d, "S01")["numbers"][0]["ref"] = "A.goals_for_avg"  # 1.9 != 2.3
    expect_violation("NS-10", "narration_script", d, c)
