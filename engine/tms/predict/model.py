"""Dixon-Coles (1997) goals model: independent Poisson scores with a low-score dependence correction tau.

    P(X=x, Y=y) = tau(x, y) * Pois(x; lam) * Pois(y; mu)          (x = home goals, y = away goals)
    tau(0,0) = 1 - lam*mu*rho   tau(0,1) = 1 + lam*rho   tau(1,0) = 1 + mu*rho   tau(1,1) = 1 - rho   else 1

The matrix is truncated at max_goals per side and renormalised to sum to 1. rho is clamped per match to the range in
which every tau is >= 0. rho = 0 is exactly the independent-Poisson model.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

import numpy as np

from tms.predict import OUTCOMES


def poisson_pmf(lam: float, max_goals: int) -> np.ndarray:
    k = np.arange(max_goals + 1)
    logp = -lam + k * math.log(lam) - np.array([math.lgamma(i + 1) for i in k])
    return np.exp(logp)


def rho_range(lam: float, mu: float) -> tuple[float, float]:
    """Interval of rho for which all four tau factors are non-negative."""
    lo = max(-1.0 / lam, -1.0 / mu)
    hi = min(1.0 / (lam * mu), 1.0)
    return lo, hi


def effective_rho(lam: float, mu: float, rho: float) -> float:
    lo, hi = rho_range(lam, mu)
    return min(max(rho, lo), hi)


def score_matrix(lam: float, mu: float, rho: float = 0.0, max_goals: int = 10) -> np.ndarray:
    """M[i, j] = P(home scores i, away scores j), i, j in 0..max_goals, renormalised to sum 1."""
    if not (lam > 0 and mu > 0):
        raise ValueError(f"expected goals must be > 0 (got {lam}, {mu})")
    m = np.outer(poisson_pmf(lam, max_goals), poisson_pmf(mu, max_goals))
    r = effective_rho(lam, mu, rho)
    m[0, 0] *= 1 - lam * mu * r
    m[0, 1] *= 1 + lam * r
    m[1, 0] *= 1 + mu * r
    m[1, 1] *= 1 - r
    m = np.clip(m, 0.0, None)
    return m / m.sum()


def outcome_probs(m: np.ndarray) -> dict[str, float]:
    return {"home": float(np.tril(m, -1).sum()), "draw": float(np.trace(m)), "away": float(np.triu(m, 1).sum())}


def result_of(home_goals: int, away_goals: int) -> str:
    return "home" if home_goals > away_goals else "draw" if home_goals == away_goals else "away"


def _ranked(m: np.ndarray) -> list[tuple[int, int, float]]:
    """All cells sorted by probability desc, ties by (home goals, away goals) asc — deterministic."""
    cells = [(i, j, float(m[i, j])) for i in range(m.shape[0]) for j in range(m.shape[1])]
    return sorted(cells, key=lambda c: (-c[2], c[0], c[1]))


def top_scorelines(m: np.ndarray, n: int) -> list[dict]:
    return [{"home": i, "away": j, "p": p} for i, j, p in _ranked(m)[:n]]


def best_scoreline_for(m: np.ndarray, result: str) -> tuple[int, int]:
    for i, j, _ in _ranked(m):
        if result_of(i, j) == result:
            return i, j
    raise ValueError(f"no scoreline with result {result}")  # unreachable for max_goals >= 1


def expected_goals(m: np.ndarray) -> tuple[float, float]:
    k = np.arange(m.shape[0])
    return float(m.sum(axis=1) @ k), float(m.sum(axis=0) @ k)


def reweight_to(m: np.ndarray, target: Mapping[str, float]) -> np.ndarray:
    """Rescale the matrix so each result's total mass equals target[result] (shape within a result kept)."""
    base = outcome_probs(m)
    out = m.copy()
    n = m.shape[0]
    for i in range(n):
        for j in range(n):
            r = result_of(i, j)
            out[i, j] = m[i, j] * (target[r] / base[r]) if base[r] > 0 else 0.0
    return out / out.sum()


def _values(probs: Mapping[str, float] | Iterable[float]) -> list[float]:
    return [float(probs[o]) for o in OUTCOMES] if isinstance(probs, Mapping) else [float(p) for p in probs]


def entropy(probs: Mapping[str, float] | Iterable[float]) -> float:
    """Shannon entropy in nats (natural log). 3 outcomes: 0 (certain) .. ln 3 = 1.0986 (uniform)."""
    return float(-sum(p * math.log(p) for p in _values(probs) if p > 0))


def margin(probs: Mapping[str, float] | Iterable[float]) -> float:
    """Largest minus second-largest probability."""
    v = sorted(_values(probs), reverse=True)
    return v[0] - v[1]


def argmax_outcome(probs: Mapping[str, float]) -> str:
    """Most likely outcome; exact ties resolve in the order home, draw, away."""
    return max(OUTCOMES, key=lambda o: (probs[o], -OUTCOMES.index(o)))


def confidence_from(h: float, mrg: float, thresholds: Mapping[str, Mapping[str, float]]) -> str:
    """First level (high, then medium) whose max_entropy and min_margin both hold; otherwise low."""
    for level in ("high", "medium"):
        t = thresholds[level]
        if h <= t["max_entropy"] and mrg >= t["min_margin"]:
            return level
    return "low"


def confidence_label(probs: Mapping[str, float], thresholds: Mapping[str, Mapping[str, float]]) -> str:
    return confidence_from(entropy(probs), margin(probs), thresholds)


def round_probs(probs: Mapping[str, float], ndigits: int = 4) -> dict[str, float]:
    """Round to ndigits; the rounding residual goes to the largest outcome so the three sum to exactly 1."""
    r = {o: round(float(probs[o]), ndigits) for o in OUTCOMES}
    top = argmax_outcome(r)
    r[top] = round(1.0 - sum(r[o] for o in OUTCOMES if o != top), ndigits)
    return r
