"""Market blend and analyst adjustments.

Market: decimal odds o_k -> raw implied q_k = 1/o_k; the bookmaker margin (sum q_k - 1) is removed by proportional
normalisation p_k = q_k / sum(q). blended = (1 - w) * model + w * market, w = market.blend_weight when all three
fixture.odds_home|draw|away facts are present, else 0.

Adjustments (artifacts/match_analysis.json -> prediction_adjustments, applied in order): for {outcome, delta_pp}
the outcome gains delta_pp/100 and the other two outcomes give up the same amount in proportion to their current
probability (so "+5 pp home" really moves home by 5 points). Each |delta_pp| <= adjustments.max_abs_delta_pp.
After every adjustment the probabilities are clipped into adjustments.clip ([0.02, 0.96]) and renormalised
(exactly: clipped outcomes are pinned at the bound and the remaining mass is shared by the others proportionally).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from tms.predict import OUTCOMES, PredictInputError, config

ODDS_KEYS = {"home": "fixture.odds_home", "draw": "fixture.odds_draw", "away": "fixture.odds_away"}


def implied_from_odds(odds: Mapping[str, float]) -> dict[str, float]:
    for o in OUTCOMES:
        v = odds[o]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 1.0:
            raise PredictInputError(f"decimal odds for {o} must be a number > 1.0, got {v!r}")
    q = {o: 1.0 / float(odds[o]) for o in OUTCOMES}
    total = sum(q.values())
    return {o: q[o] / total for o in OUTCOMES}


def odds_from_facts(facts: Mapping[str, Any]) -> tuple[dict[str, float] | None, list[tuple[str, float]]]:
    """All three odds facts present and usable -> (odds, inputs used); otherwise (None, [])."""
    odds, used = {}, []
    for o, key in ODDS_KEYS.items():
        f = facts.get(key)
        if not isinstance(f, Mapping) or f.get("status") == "conflict":
            return None, []
        odds[o] = f.get("value")
        used.append((key, f.get("value")))
    implied_from_odds(odds)  # raises on implausible odds
    return {o: float(v) for o, v in odds.items()}, [(k, float(v)) for k, v in used]


def blend(model: Mapping[str, float], market: Mapping[str, float] | None, weight: float) -> dict[str, float]:
    if market is None or weight == 0:
        return {o: float(model[o]) for o in OUTCOMES}
    return {o: (1 - weight) * model[o] + weight * market[o] for o in OUTCOMES}


def clip_renormalise(probs: Mapping[str, float], lo: float, hi: float) -> dict[str, float]:
    """Project onto {lo <= p_k <= hi, sum p = 1}: pin violators at their bound, rescale the rest; repeat."""
    if len(OUTCOMES) * lo > 1 + 1e-12 or len(OUTCOMES) * hi < 1 - 1e-12:
        raise ValueError(f"infeasible clip band [{lo}, {hi}]")
    p = {o: max(float(probs[o]), 0.0) for o in OUTCOMES}
    fixed: dict[str, float] = {}
    for _ in range(len(OUTCOMES) + 1):
        free = [o for o in OUTCOMES if o not in fixed]
        mass = 1.0 - sum(fixed.values())
        s = sum(p[o] for o in free)
        q = {o: (p[o] * mass / s if s > 0 else mass / len(free)) for o in free}
        viol = {o: (lo if q[o] < lo else hi) for o in free if q[o] < lo - 1e-15 or q[o] > hi + 1e-15}
        if not viol:
            return {o: fixed.get(o, q.get(o, 0.0)) for o in OUTCOMES}
        fixed.update(viol)
    return {o: fixed.get(o, 0.0) for o in OUTCOMES}  # every outcome pinned (only when the band is tight)


def apply_adjustments(probs: Mapping[str, float], adjustments: Iterable[Mapping[str, Any]],
                      cfg: Mapping[str, Any] | None = None) -> tuple[dict[str, float], list[dict]]:
    cfg = cfg or config()
    max_abs = float(cfg["adjustments"]["max_abs_delta_pp"])
    lo, hi = cfg["adjustments"]["clip"]
    p = clip_renormalise(probs, lo, hi)
    applied: list[dict] = []
    for i, adj in enumerate(adjustments):
        o, d = adj.get("outcome"), adj.get("delta_pp")
        if o not in OUTCOMES:
            raise PredictInputError(f"prediction_adjustments[{i}].outcome must be one of {OUTCOMES}, got {o!r}")
        if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or abs(d) > max_abs:
            raise PredictInputError(f"prediction_adjustments[{i}].delta_pp must be within +/-{max_abs:g}, got {d!r}")
        delta = d / 100.0
        others = [k for k in OUTCOMES if k != o]
        rest = sum(p[k] for k in others)
        q = dict(p)
        q[o] = p[o] + delta
        for k in others:
            q[k] = p[k] - delta * (p[k] / rest if rest > 0 else 1.0 / len(others))
        p = clip_renormalise(q, lo, hi)
        applied.append({"outcome": o, "delta_pp": d, "reason": adj.get("reason", ""), "refs": list(adj.get("refs", []))})
    return p, applied
