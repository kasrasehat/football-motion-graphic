"""Rolling-origin backtest: gradient, synthetic season with known strengths, determinism, CSV handling."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from scipy.optimize import check_grad

from tms.predict import PredictInputError
from tms.predict import backtest as BT

pytestmark = pytest.mark.fast


@pytest.fixture(scope="module")
def season():
    return BT.generate_season(20, seed=7)


def test_synthetic_season_shape(season):
    matches, truth = season
    assert len(matches) == 380
    pairs = {(m.home, m.away) for m in matches}
    assert len(pairs) == 380  # every ordered pairing exactly once
    by_day: dict = {}
    for m in matches:
        by_day.setdefault(m.date, []).append(m)
    assert len(by_day) == 38 and all(len(v) == 10 for v in by_day.values())
    assert all(len({t for m in v for t in (m.home, m.away)}) == 20 for v in by_day.values())
    assert 2.3 < sum(m.home_goals + m.away_goals for m in matches) / 380 < 3.2
    assert BT.generate_season(20, seed=7) == season  # seeded: identical


def test_gradient_matches_finite_differences(season):
    matches, truth = season
    teams = truth["teams"]
    idx = {t: k for k, t in enumerate(teams)}
    hi = np.array([idx[m.home] for m in matches])
    ai = np.array([idx[m.away] for m in matches])
    x = np.array([m.home_goals for m in matches], float)
    y = np.array([m.away_goals for m in matches], float)
    w = np.full(len(matches), 1 / len(matches))
    theta = np.random.default_rng(0).normal(0, 0.2, 3 + 2 * len(teams))
    theta[2] = -0.05
    args = (hi, ai, x, y, w, len(teams), 0.01)
    err = check_grad(lambda t: BT._nll_and_grad(t, *args)[0], lambda t: BT._nll_and_grad(t, *args)[1], theta)
    assert err < 1e-5


def test_full_season_fit_recovers_known_strengths(season):
    matches, truth = season
    f = BT.fit(matches, truth["teams"], matches[-1].date, {"backtest": {
        "half_life_days": 1e9, "ridge": 0.001, "rho_bounds": [-0.2, 0.2], "max_iter": 500}})
    assert f.converged
    att_true = np.array([truth["attack"][t] for t in truth["teams"]])
    def_true = np.array([truth["defence"][t] for t in truth["teams"]])
    assert np.corrcoef(att_true, f.attack)[0, 1] > 0.8
    assert np.corrcoef(def_true, f.defence)[0, 1] > 0.6
    assert 1.1 < np.exp(f.g) < 1.6  # truth 1.30


def test_backtest_beats_base_rate_baseline(season):
    matches, _ = season
    rep = BT.run(matches, warmup=100)
    assert rep["matches"] == 380 and rep["evaluated"] == 280 and rep["refits"] == 28
    assert rep["model"]["brier"] < rep["baseline"]["brier"], rep
    assert rep["model"]["log_loss"] < rep["baseline"]["log_loss"], rep
    assert rep["brier_skill"] > 0.02
    assert rep["last_fit"]["converged"]
    assert BT.run(matches, warmup=100) == rep  # deterministic


def test_no_lookahead(season):
    """Predictions for a date use only earlier dates: changing a result on the last date changes no prediction."""
    matches, _ = season
    window = list(matches[:120])  # 12 match days; days 11 and 12 are scored
    tampered = window[:-1] + [BT.Match(window[-1].date, window[-1].home, window[-1].away, 9, 0)]
    a, b = BT.run(window, warmup=100, details=True), BT.run(tampered, warmup=100, details=True)
    assert [r["model"] for r in a["predictions"]] == [r["model"] for r in b["predictions"]]
    assert [r["baseline"] for r in a["predictions"]] == [r["baseline"] for r in b["predictions"]]
    assert a["model"] != b["model"]  # ...only the score of that match changed


def test_csv_roundtrip_and_errors(tmp_path, season):
    matches, _ = season
    p = tmp_path / "season.csv"
    BT.write_csv(p, matches)
    assert BT.read_csv(p) == sorted(matches, key=lambda m: m.date)
    bad = tmp_path / "bad.csv"
    bad.write_text("date,home,away,home_goals\n2025-01-01,A,B,1\n", encoding="utf-8")
    with pytest.raises(PredictInputError, match="header"):
        BT.read_csv(bad)
    bad.write_text("date,home,away,home_goals,away_goals\n2025-01-01,A,B,one,0\n", encoding="utf-8")
    with pytest.raises(PredictInputError, match="line 2"):
        BT.read_csv(bad)
    with pytest.raises(PredictInputError, match="nothing to evaluate"):
        BT.run([BT.Match(date(2025, 1, 1), "A", "B", 1, 0)], warmup=5)
