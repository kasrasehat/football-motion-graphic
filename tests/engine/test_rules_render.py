"""RP / FQ rules: fixtures clean; each mutation triggers its rule."""
from __future__ import annotations

import pytest

from tms.validate.registry import Context
from tests.helpers import expect_clean, expect_violation, fixture

pytestmark = pytest.mark.fast


def rp():
    return fixture("render_props")


def rr():
    return fixture("render_report")


def test_fixtures_clean():
    expect_clean("render_props", rp(), Context(artifacts={"brief": fixture("brief")}))
    expect_clean("render_report", rr())


def test_RP01_track_length():
    d = rp()
    d["tracks"]["players"]["H2"] = d["tracks"]["players"]["H2"][:-2]
    expect_violation("RP-01", "render_props", d)


def test_RP02_orientation_vs_brief():
    b = fixture("brief")
    b["aspect"] = "9:16"
    expect_violation("RP-02", "render_props", rp(), Context(artifacts={"brief": b}))


def test_RP03_window_outside_video():
    d = rp()
    d["overlays"][0]["to"] = d["durationInFrames"] + 10
    expect_violation("RP-03", "render_props", d)


def test_RP04_stale_inputs(tmp_projects):
    from tms.state import project as P
    from tests.helpers import place
    pr = P.init("fx-ifb-442", "tactic", "t", dry_run=True)
    place(pr.dir, "brief", fixture("brief"))
    d = rp()
    d["inputs"] = {"brief": "0" * 64}
    expect_violation("RP-04", "render_props", d, Context(project_dir=pr.dir))


def test_RP05_huge_props():
    d = rp()
    d["debug"] = {"overlay": False}
    d["graphics"] = [{"id": "G", "template": "text_card", "from": 0, "to": 10, "data": {"x": "y" * 9_000_000}, "reveals": []}]
    expect_violation("RP-05", "render_props", d)


def test_RP06_teleporting_token():
    d = rp()
    arr = d["tracks"]["players"]["H5"]
    for f in range(40, 50):
        arr[2 * f] += 300 * (f - 39)
    expect_violation("RP-06", "render_props", d)


@pytest.mark.parametrize("rid", ["FQ-01", "FQ-02", "FQ-03", "FQ-04", "FQ-05", "FQ-06", "FQ-07", "FQ-08"])
def test_FQ_failed_check_is_reported(rid):
    d = rr()
    c = next(x for x in d["checks"] if x["rule"] == rid)
    c["ok"] = False
    c["detail"] = "measured value out of range"
    expect_violation(rid, "render_report", d)
