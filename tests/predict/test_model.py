"""Dixon-Coles model: probability laws and invariances (hypothesis property tests, derandomised)."""
from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import poisson

from tms.predict import OUTCOMES, config
from tms.predict import model as M

pytestmark = pytest.mark.fast
PROPS = settings(max_examples=60, deadline=None, derandomize=True, database=None)
lam_s = st.floats(min_value=0.2, max_value=3.5, allow_nan=False, allow_infinity=False)
rho_s = st.floats(min_value=-0.3, max_value=0.3, allow_nan=False, allow_infinity=False)
goals_s = st.integers(min_value=6, max_value=15)


@PROPS
@given(lam_s, lam_s, rho_s, goals_s)
def test_matrix_and_outcomes_sum_to_one(lam, mu, rho, n):
    m = M.score_matrix(lam, mu, rho, n)
    assert m.shape == (n + 1, n + 1)
    assert (m >= 0).all()
    assert m.sum() == pytest.approx(1.0, abs=1e-12)
    p = M.outcome_probs(m)
    assert sum(p.values()) == pytest.approx(1.0, abs=1e-12)
    assert all(0 <= p[o] <= 1 for o in OUTCOMES)


@PROPS
@given(lam_s, lam_s, rho_s)
def test_swapping_teams_swaps_home_and_away(lam, mu, rho):
    """With no home advantage, team order is the only asymmetry: swapping lambdas transposes the matrix."""
    a, b = M.score_matrix(lam, mu, rho), M.score_matrix(mu, lam, rho)
    np.testing.assert_allclose(a, b.T, atol=1e-12)
    pa, pb = M.outcome_probs(a), M.outcome_probs(b)
    assert pa["home"] == pytest.approx(pb["away"], abs=1e-12)
    assert pa["away"] == pytest.approx(pb["home"], abs=1e-12)
    assert pa["draw"] == pytest.approx(pb["draw"], abs=1e-12)


@PROPS
@given(lam_s, lam_s, rho_s, st.floats(min_value=1.05, max_value=2.0))
def test_more_home_attack_more_home_wins(lam, mu, rho, factor):
    lam2 = min(lam * factor, 4.0)
    if lam2 <= lam * 1.01:
        return
    assert M.outcome_probs(M.score_matrix(lam2, mu, rho))["home"] > M.outcome_probs(M.score_matrix(lam, mu, rho))["home"]


@PROPS
@given(lam_s, lam_s, goals_s)
def test_rho_zero_is_independent_poisson(lam, mu, n):
    k = np.arange(n + 1)
    ind = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    np.testing.assert_allclose(M.score_matrix(lam, mu, 0.0, n), ind / ind.sum(), rtol=1e-10, atol=1e-14)


def test_tau_corrects_only_low_scores():
    lam, mu, rho = 1.3, 1.1, -0.1
    dc, ind = M.score_matrix(lam, mu, rho, 10), M.score_matrix(lam, mu, 0.0, 10)
    ratio = dc / ind
    assert ratio[0, 0] == pytest.approx(1 - lam * mu * rho, rel=1e-6)
    assert ratio[1, 1] == pytest.approx(1 - rho, rel=1e-6)
    assert ratio[0, 1] == pytest.approx(1 + lam * rho, rel=1e-6)
    assert ratio[1, 0] == pytest.approx(1 + mu * rho, rel=1e-6)
    assert ratio[2, 3] == pytest.approx(1.0, rel=1e-6)  # tau preserves total mass: no renormalisation drift
    assert dc[0, 0] > ind[0, 0] and dc[1, 1] > ind[1, 1]  # rho < 0 inflates 0-0 and 1-1


def test_rho_clamped_where_tau_would_go_negative():
    lam, mu = 4.0, 4.0
    assert M.effective_rho(lam, mu, -0.3) == pytest.approx(-0.25)
    assert M.effective_rho(lam, mu, 0.3) == pytest.approx(1 / 16)
    assert (M.score_matrix(lam, mu, -0.3) >= 0).all()


def test_expected_goals_close_to_lambdas():
    eh, ea = M.expected_goals(M.score_matrix(1.7, 1.2, -0.08, 12))
    assert eh == pytest.approx(1.7, abs=1e-3) and ea == pytest.approx(1.2, abs=1e-3)


def test_top_scorelines_sorted_and_deterministic():
    m = M.score_matrix(1.4, 1.4, 0.0, 10)
    top = M.top_scorelines(m, 6)
    ps = [s["p"] for s in top]
    assert ps == sorted(ps, reverse=True)
    assert top == M.top_scorelines(m, 6)
    i, j = M.best_scoreline_for(m, "away")
    assert i < j


def test_entropy_bounds_and_confidence_thresholds():
    th = config()["confidence"]
    assert M.entropy({"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}) == pytest.approx(math.log(3))
    assert M.entropy({"home": 1.0, "draw": 0.0, "away": 0.0}) == 0.0
    assert M.confidence_label({"home": 0.72, "draw": 0.17, "away": 0.11}, th) == "high"
    assert M.confidence_label({"home": 0.55, "draw": 0.25, "away": 0.20}, th) == "medium"
    assert M.confidence_label({"home": 0.47, "draw": 0.24, "away": 0.29}, th) == "low"
    # two-horse race: low entropy but no clear favourite -> low
    assert M.confidence_label({"home": 0.46, "draw": 0.08, "away": 0.46}, th) == "low"


@PROPS
@given(st.floats(0.01, 1), st.floats(0.01, 1), st.floats(0.01, 1))
def test_round_probs_sum_exactly_one(a, b, c):
    s = a + b + c
    r = M.round_probs({"home": a / s, "draw": b / s, "away": c / s}, 4)
    assert sum(r.values()) == pytest.approx(1.0, abs=1e-9)
