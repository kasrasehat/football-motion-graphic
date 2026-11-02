"""TS rules: fixture clean; each mutation triggers its rule; scaffolds are valid for every template x phase."""
from __future__ import annotations

import itertools

import pytest

from tms.tactic import formations as F
from tms.tactic.geometry import to_abs, to_norm
from tms.tactic.scaffold import scaffold
from tms.validate.registry import Context
from tests.helpers import expect_clean, expect_violation, findings, fixture

pytestmark = pytest.mark.fast


def ctx():
    return Context(artifacts={"brief": fixture("brief")})


def spec():
    return fixture("tactic_spec")


def player(d, pid):
    return next(p for t in "HA" for p in d["teams"][t]["players"] if p["id"] == pid)


def test_fixture_clean():
    expect_clean("tactic_spec", spec(), ctx())


def test_TS01_duplicate_id():
    d = spec()
    player(d, "H3")["id"] = "H2"
    expect_violation("TS-01", "tactic_spec", d, ctx())


def test_TS02_two_goalkeepers():
    d = spec()
    p = player(d, "H5")
    p.update(role="GK", line=0)
    expect_violation("TS-02", "tactic_spec", d, ctx())


def test_TS03_formation_not_ten():
    d = spec()
    d["teams"]["A"]["formation_base"] = "4-4-3"
    expect_violation("TS-03", "tactic_spec", d, ctx())


def test_TS04_line_counts():
    d = spec()
    player(d, "H6")["line"] = 3
    expect_violation("TS-04", "tactic_spec", d, ctx())


def test_TS05_lines_out_of_order():
    d = spec()
    for pid in ("H6", "H2"):
        player(d, pid)["pos"][0] = 24.0
    expect_violation("TS-05", "tactic_spec", d, ctx())


def test_TS06_left_right_swapped():
    d = spec()
    player(d, "A3")["pos"][1], player(d, "A2")["pos"][1] = 56, 12
    expect_violation("TS-06", "tactic_spec", d, ctx())


def test_TS07_winger_in_the_middle():
    d = spec()
    player(d, "A7")["pos"][1] = 34  # RM drifting central without justification
    expect_violation("TS-07", "tactic_spec", d, ctx())


def test_TS08_out_of_bounds():
    d = spec()
    player(d, "H11")["pos"][1] = 68.5
    expect_violation("TS-08", "tactic_spec", d, ctx())


def test_TS09_teammates_too_close():
    d = spec()
    player(d, "H8")["pos"] = [58, 23]  # 2.2 m from... make it close to H10? use H9
    player(d, "H8")["pos"] = [66, 32]
    expect_violation("TS-09", "tactic_spec", d, ctx())


def test_TS09_opponents_overlap():
    d = spec()
    # A6 (normalized 42,40) is absolute (63,28); put H8 on top of it
    player(d, "H8")["pos"] = [63.3, 28.2]
    expect_violation("TS-09", "tactic_spec", d, ctx())


def test_TS10_goalkeeper_far_out():
    d = spec()
    player(d, "H1")["pos"][0] = 35
    expect_violation("TS-10", "tactic_spec", d, ctx())


def test_TS11_duplicate_numbers():
    d = spec()
    player(d, "H3")["number"] = 2
    expect_violation("TS-11", "tactic_spec", d, ctx())


def test_TS12_too_many_principles():
    d = spec()
    extra = dict(d["principles"][0])
    for i in (4, 5, 6):
        d["principles"].append(dict(extra, id=f"P{i}"))
    expect_violation("TS-12", "tactic_spec", d, ctx())


def test_TS13_holder_wrong_team():
    d = spec()
    d["ball"]["holder"] = "A9"
    expect_violation("TS-13", "tactic_spec", d, ctx())


def test_TS14_defensive_block_too_stretched():
    d = spec()
    player(d, "A9")["pos"][0] = 80  # striker 50 m ahead of the back line
    expect_violation("TS-14", "tactic_spec", d, ctx())


def test_TS15_offside_in_snapshot():
    d = spec()
    player(d, "H9")["pos"][0] = 82  # beyond Blues' line at absolute x ~77
    expect_violation("TS-15", "tactic_spec", d, ctx())


def test_TS16_dangling_reference():
    d = spec()
    d["counters"][0]["targets"] = "W9"
    expect_violation("TS-16", "tactic_spec", d, ctx())


def test_TS17_focus_differs_from_brief():
    d = spec()
    d["focus_team"] = "both"
    d["ball"]["holder"] = "H4"
    expect_violation("TS-17", "tactic_spec", d, ctx())


# ---------------------------------------------------------------- engine
def test_templates_internally_consistent():
    assert F.validate_templates() == []
    assert len(F.template_names()) >= 12


def test_rotation_keeps_left_and_right():
    # Away left-back (team-normalized small y) must appear at large absolute y (it faces the home right wing).
    assert to_abs("A", (30, 10)) == (75, 58)
    assert to_norm("A", to_abs("A", (12.5, 7.0))) == (12.5, 7.0)
    assert to_abs("H", (30, 10)) == (30, 10)


def _filled(s: dict) -> dict:
    holder_team = s["ball"]["holder"][0]
    pid = next(p["id"] for p in s["teams"][holder_team]["players"] if p["role"] != "GK")
    s.update(title="Scaffold check", summary="A scaffold filled with minimal content for validation.")
    s["principles"] = [{"id": "P1", "name": "Test principle", "statement": "A statement long enough to pass.",
                        "players": [pid], "visual_proof": "Something visible on the pitch"}]
    return s


PHASES = ["build_up", "progression", "final_third", "high_press", "mid_block", "low_block", "counter_press"]


@pytest.mark.parametrize("home,away", [(h, a) for h, a in itertools.product(F.template_names(), repeat=2)
                                       if (F.template_names().index(h) + F.template_names().index(a)) % 4 == 0])
@pytest.mark.parametrize("phase", PHASES)
def test_scaffolds_pass_all_error_rules(home, away, phase):
    s = _filled(scaffold("fx-ifb-442", phase, "H", home, away))
    brief = fixture("brief")
    errs = [(f.rule, f.location, f.message) for f in findings("tactic_spec", s, Context(artifacts={"brief": brief}))
            if f.severity == "error"]
    assert not errs, errs


def test_scaffold_holder_and_possession():
    s = scaffold("x", "high_press", "H", "4-3-3", "4-2-3-1")
    assert s["ball"]["holder"].startswith("A")  # H presses, A has the ball
    s = scaffold("x", "build_up", "A", "4-4-2", "4-3-3")
    assert s["ball"]["holder"].startswith("A")
