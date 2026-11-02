"""Market de-vig + blend and bounded analyst adjustments."""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tms.predict import OUTCOMES, PredictInputError, config
from tms.predict import blend as B
from tests.predict._util import fact

pytestmark = pytest.mark.fast
PROPS = settings(max_examples=80, deadline=None, derandomize=True, database=None)
LO, HI = config()["adjustments"]["clip"]


@st.composite
def probs_s(draw):
    v = [draw(st.floats(0.01, 1.0)) for _ in OUTCOMES]
    s = sum(v)
    return {o: x / s for o, x in zip(OUTCOMES, v)}


adj_s = st.fixed_dictionaries({
    "outcome": st.sampled_from(OUTCOMES),
    "delta_pp": st.floats(-10, 10, allow_nan=False),
    "reason": st.just("Key striker ruled out with injury."),
    "refs": st.just(["C-001"]),
})


def test_devig_proportional():
    p = B.implied_from_odds({"home": 2.0, "draw": 3.5, "away": 4.0})
    raw = [1 / 2.0, 1 / 3.5, 1 / 4.0]
    assert sum(p.values()) == pytest.approx(1.0)
    assert p["home"] == pytest.approx(raw[0] / sum(raw))
    assert p["home"] > p["draw"] > p["away"]


def test_odds_from_facts_requires_all_three():
    facts = {"fixture.odds_home": fact(2.0), "fixture.odds_draw": fact(3.5)}
    assert B.odds_from_facts(facts) == (None, [])
    facts["fixture.odds_away"] = fact(4.0)
    odds, used = B.odds_from_facts(facts)
    assert odds == {"home": 2.0, "draw": 3.5, "away": 4.0}
    assert [k for k, _ in used] == ["fixture.odds_home", "fixture.odds_draw", "fixture.odds_away"]
    facts["fixture.odds_away"] = fact(0.9)
    with pytest.raises(PredictInputError):
        B.odds_from_facts(facts)


def test_blend_weights():
    model = {"home": 0.5, "draw": 0.3, "away": 0.2}
    market = {"home": 0.4, "draw": 0.3, "away": 0.3}
    assert B.blend(model, None, 0.35) == model
    b = B.blend(model, market, 0.35)
    assert b["home"] == pytest.approx(0.65 * 0.5 + 0.35 * 0.4)
    assert sum(b.values()) == pytest.approx(1.0)


def test_adjustment_moves_target_by_delta_pp():
    p, applied = B.apply_adjustments({"home": 0.5, "draw": 0.3, "away": 0.2},
                                     [{"outcome": "home", "delta_pp": 5, "reason": "x" * 12, "refs": ["C-001"]}])
    assert p["home"] == pytest.approx(0.55)
    assert p["draw"] == pytest.approx(0.3 - 0.05 * 0.6) and p["away"] == pytest.approx(0.2 - 0.05 * 0.4)
    assert applied == [{"outcome": "home", "delta_pp": 5, "reason": "x" * 12, "refs": ["C-001"]}]


def test_clip_band_enforced():
    p, _ = B.apply_adjustments({"home": 0.93, "draw": 0.05, "away": 0.02},
                               [{"outcome": "home", "delta_pp": 10, "reason": "x" * 12, "refs": ["C-001"]}])
    assert p["home"] == pytest.approx(HI) and p["draw"] == pytest.approx(LO) and p["away"] == pytest.approx(LO)


@pytest.mark.parametrize("bad", [{"outcome": "home", "delta_pp": 10.5}, {"outcome": "win", "delta_pp": 1},
                                 {"outcome": "away", "delta_pp": float("nan")}])
def test_out_of_bounds_adjustment_rejected(bad):
    with pytest.raises(PredictInputError):
        B.apply_adjustments({"home": 0.5, "draw": 0.3, "away": 0.2}, [{**bad, "reason": "x" * 12, "refs": ["C-1"]}])


@PROPS
@given(probs_s(), st.lists(adj_s, max_size=3))
def test_adjusted_probabilities_bounded_and_renormalised(p, adjs):
    out, applied = B.apply_adjustments(p, adjs)
    assert sum(out.values()) == pytest.approx(1.0, abs=1e-9)
    assert all(LO - 1e-9 <= out[o] <= HI + 1e-9 for o in OUTCOMES)
    assert len(applied) == len(adjs)


@PROPS
@given(probs_s(), adj_s)
def test_single_adjustment_moves_target_at_most_its_delta(p, adj):
    start = B.clip_renormalise(p, LO, HI)
    out, _ = B.apply_adjustments(p, [adj])
    moved = (out[adj["outcome"]] - start[adj["outcome"]]) * 100
    assert abs(moved) <= abs(adj["delta_pp"]) + 1e-7
    assert moved * adj["delta_pp"] >= -1e-9  # never moves the wrong way


@PROPS
@given(probs_s())
def test_clip_renormalise_is_a_projection(p):
    q = B.clip_renormalise(p, LO, HI)
    assert sum(q.values()) == pytest.approx(1.0, abs=1e-12)
    assert B.clip_renormalise(q, LO, HI) == pytest.approx(q)
