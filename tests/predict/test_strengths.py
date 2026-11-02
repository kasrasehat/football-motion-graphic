"""Lambda formula from dossier facts: hand-checked numbers, venue splits, xG blend, overrides, errors."""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tms.predict import PredictInputError, config
from tms.predict import model as M
from tms.predict import strengths as S
from tests.predict._util import fact

pytestmark = pytest.mark.fast
PROPS = settings(max_examples=50, deadline=None, derandomize=True, database=None)


def base_facts(**kv) -> dict:
    f = {"H.goals_for_avg": 2.0, "H.goals_against_avg": 1.0, "A.goals_for_avg": 1.5, "A.goals_against_avg": 1.2,
         "fixture.league_avg_goals": 1.4, "fixture.home_advantage": 1.21}
    f.update(kv)
    return {k: fact(v) for k, v in f.items() if v is not None}


def test_hand_checked_example():
    """L=1.4, HA=1.21 (s=1.1): lambda_home = s*gf_H*ga_A/L = 1.1*2.0*1.2/1.4; lambda_away = gf_A*ga_H/(s*L)."""
    r = S.compute(base_facts())
    assert r.lam_home == pytest.approx(1.1 * 2.0 * 1.2 / 1.4)   # 1.885714
    assert r.lam_away == pytest.approx(1.5 * 1.0 / (1.1 * 1.4))  # 0.974026
    assert r.lam_home == pytest.approx(1.885714, abs=1e-6)
    assert r.lam_away == pytest.approx(0.974026, abs=1e-6)
    assert r.ratings["attack_H"] == pytest.approx(2.0 / 1.4)
    assert r.ratings["defence_A"] == pytest.approx(1.2 / 1.4)
    assert [k for k, _ in r.inputs_used] == ["fixture.league_avg_goals", "fixture.home_advantage", "H.goals_for_avg",
                                             "A.goals_against_avg", "A.goals_for_avg", "H.goals_against_avg"]


def test_xg_blend_uses_configured_weight():
    w = config()["strengths"]["xg_weight"]
    r = S.compute(base_facts(**{"H.xg_for_avg": 1.6}))
    att = (1 - w) * 2.0 / 1.4 + w * 1.6 / 1.4
    assert r.lam_home == pytest.approx(1.1 * 1.4 * att * 1.2 / 1.4)
    assert ("H.xg_for_avg", 1.6) in r.inputs_used


def test_venue_split_preferred_and_measured_against_venue_baseline():
    r = S.compute(base_facts(**{"H.home_goals_for_avg": 2.42}))
    assert r.ratings["attack_H"] == pytest.approx(2.42 / (1.4 * 1.1))
    assert r.lam_home == pytest.approx(2.42 * 1.2 / 1.4)
    keys = [k for k, _ in r.inputs_used]
    assert "H.home_goals_for_avg" in keys and "H.goals_for_avg" not in keys


def test_defaults_from_config_when_fixture_facts_absent():
    cfg = config()["strengths"]
    r = S.compute(base_facts(**{"fixture.league_avg_goals": None, "fixture.home_advantage": None}))
    assert r.league_avg == cfg["league_avg_goals"] and r.home_advantage == cfg["home_advantage"]
    assert all(not k.startswith("fixture.") for k, _ in r.inputs_used)


def test_missing_required_facts_listed():
    with pytest.raises(PredictInputError) as e:
        S.compute({"H.goals_for_avg": fact(2.0), "A.goals_for_avg": fact(1.5)})
    assert e.value.missing == ["H.goals_against_avg", "A.goals_against_avg"]
    assert "H.goals_against_avg (or H.home_goals_against_avg)" in str(e.value)


def test_conflicted_fact_is_unusable():
    f = base_facts()
    f["H.goals_for_avg"]["status"] = "conflict"
    with pytest.raises(PredictInputError, match="unresolved conflicts: H.goals_for_avg"):
        S.compute(f)


@pytest.mark.parametrize("key,value", [("fixture.league_avg_goals", 2.8), ("fixture.home_advantage", 2.5),
                                       ("H.goals_for_avg", "lots"), ("A.goals_against_avg", -1)])
def test_implausible_values_rejected(key, value):
    with pytest.raises(PredictInputError):
        S.compute(base_facts(**{key: value}))


@PROPS
@given(st.floats(0.3, 3.0), st.floats(0.3, 3.0), st.floats(0.3, 3.0), st.floats(0.3, 3.0))
def test_swap_teams_with_no_home_advantage_swaps_probabilities(hf, ha, af, aa):
    one = S.compute(base_facts(**{"H.goals_for_avg": hf, "H.goals_against_avg": ha, "A.goals_for_avg": af,
                                  "A.goals_against_avg": aa, "fixture.home_advantage": 1.0}))
    two = S.compute(base_facts(**{"H.goals_for_avg": af, "H.goals_against_avg": aa, "A.goals_for_avg": hf,
                                  "A.goals_against_avg": ha, "fixture.home_advantage": 1.0}))
    assert one.lam_home == pytest.approx(two.lam_away) and one.lam_away == pytest.approx(two.lam_home)
    p1 = M.outcome_probs(M.score_matrix(one.lam_home, one.lam_away, -0.08))
    p2 = M.outcome_probs(M.score_matrix(two.lam_home, two.lam_away, -0.08))
    assert p1["home"] == pytest.approx(p2["away"], abs=1e-9) and p1["draw"] == pytest.approx(p2["draw"], abs=1e-9)


@PROPS
@given(st.floats(0.3, 2.5), st.floats(1.05, 1.6))
def test_more_home_goals_for_raises_home_win_probability(hf, factor):
    def p_home(v):
        r = S.compute(base_facts(**{"H.goals_for_avg": v}))
        return M.outcome_probs(M.score_matrix(r.lam_home, r.lam_away, -0.08))["home"]
    assert p_home(hf * factor) > p_home(hf)


def test_home_advantage_favours_home():
    even = base_facts(**{"H.goals_for_avg": 1.4, "H.goals_against_avg": 1.4, "A.goals_for_avg": 1.4,
                         "A.goals_against_avg": 1.4})
    r = S.compute(even)
    assert r.lam_home / r.lam_away == pytest.approx(1.21)
    assert math.isclose(r.lam_home * r.lam_away, 1.4 * 1.4)
