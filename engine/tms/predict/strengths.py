"""Expected goals (lambda) for a fixture from match_dossier facts — a documented, deterministic formula.

Notation: L = league average goals per TEAM per match, HA = home-advantage ratio, s = sqrt(HA).
An average home side is expected to score Bh = L*s, an average away side Ba = L/s.

Ratings are ratios to the baseline of the venue the statistic was measured at:
    attack_H  = gf_H / (Bh if gf_H is a home split  else L)      gf = goals scored per match
    defence_A = ga_A / (Bh if ga_A is an away split else L)      ga = goals conceded per match (>1 = leaky)
    attack_A  = gf_A / (Ba if gf_A is an away split else L)
    defence_H = ga_H / (Ba if ga_H is a home split  else L)
When an xG fact exists for the same metric, its rating (computed the same way, league xG average = L) is blended:
    rating = (1 - w) * goals_rating + w * xg_rating                   w = strengths.xg_weight
Then
    lambda_home = Bh * attack_H * defence_A        lambda_away = Ba * attack_A * defence_H
(both floored at model.lambda_floor). With no venue splits and no xG this is lambda_home = s * gf_H * ga_A / L.

Fact keys (first present wins; facts whose status is "conflict" are unusable):
    H attack   H.home_goals_for_avg | H.goals_for_avg          xG: H.home_xg_for_avg | H.xg_for_avg
    H defence  H.home_goals_against_avg | H.goals_against_avg  xG: H.home_xg_against_avg | H.xg_against_avg
    A attack   A.away_goals_for_avg | A.goals_for_avg          xG: A.away_xg_for_avg | A.xg_for_avg
    A defence  A.away_goals_against_avg | A.goals_against_avg  xG: A.away_xg_against_avg | A.xg_against_avg
    L          fixture.league_avg_goals (per team per match) | config strengths.league_avg_goals
    HA         fixture.home_advantage | config strengths.home_advantage
Required minimum: a goals-for and a goals-against average for both teams (overall or venue split).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from tms.predict import PredictInputError, config

# metric -> (venue-split key, overall key) for goals and for xG; `venue` names the split ("home" for H, "away" for A)
METRICS: dict[str, dict[str, tuple[str, str]]] = {
    "attack_H": {"goals": ("H.home_goals_for_avg", "H.goals_for_avg"), "xg": ("H.home_xg_for_avg", "H.xg_for_avg")},
    "defence_A": {"goals": ("A.away_goals_against_avg", "A.goals_against_avg"),
                  "xg": ("A.away_xg_against_avg", "A.xg_against_avg")},
    "attack_A": {"goals": ("A.away_goals_for_avg", "A.goals_for_avg"), "xg": ("A.away_xg_for_avg", "A.xg_for_avg")},
    "defence_H": {"goals": ("H.home_goals_against_avg", "H.goals_against_avg"),
                  "xg": ("H.home_xg_against_avg", "H.xg_against_avg")},
}
# which baseline a venue-split statistic is measured against: the home lambda's (Bh) or the away lambda's (Ba)
SIDE = {"attack_H": "home", "defence_A": "home", "attack_A": "away", "defence_H": "away"}
REQUIRED = ("H.goals_for_avg", "H.goals_against_avg", "A.goals_for_avg", "A.goals_against_avg")


@dataclass
class Strengths:
    lam_home: float
    lam_away: float
    league_avg: float
    home_advantage: float
    ratings: dict[str, float]
    inputs_used: list[tuple[str, float]] = field(default_factory=list)


def _number(key: str, fact: Mapping[str, Any]) -> float:
    v = fact.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise PredictInputError(f"fact {key} must be a non-negative number, got {v!r}")
    return float(v)


class _Facts:
    """Reads numeric facts and records every one actually consumed (in consumption order)."""

    def __init__(self, facts: Mapping[str, Any]):
        self.facts = facts
        self.used: list[tuple[str, float]] = []
        self.conflicted: list[str] = []

    def peek(self, key: str) -> float | None:
        f = self.facts.get(key)
        if not isinstance(f, Mapping):
            return None
        if f.get("status") == "conflict":
            self.conflicted.append(key)
            return None
        return _number(key, f)

    def take(self, key: str) -> float | None:
        v = self.peek(key)
        if v is not None:
            self.used.append((key, v))
        return v

    def first(self, keys: tuple[str, str]) -> tuple[str, float] | None:
        for k in keys:
            if self.peek(k) is not None:
                return k, self.take(k)
        return None


def compute(facts: Mapping[str, Any], cfg: Mapping[str, Any] | None = None) -> Strengths:
    cfg = cfg or config()
    sc, mc = cfg["strengths"], cfg["model"]
    fx = _Facts(facts)

    split_of = {spec["goals"][1]: spec["goals"][0] for spec in METRICS.values()}
    missing = [k for k in REQUIRED if fx.peek(split_of[k]) is None and fx.peek(k) is None]
    if missing:
        need = ", ".join(f"{k} (or {split_of[k]})" for k in missing)
        extra = f"; unresolved conflicts: {', '.join(sorted(set(fx.conflicted)))}" if fx.conflicted else ""
        raise PredictInputError(
            f"match_dossier lacks the facts the prediction model needs: {need}{extra}. Required minimum: goals for "
            f"and goals against per match for both teams ({', '.join(REQUIRED)}).", missing)

    league = fx.take("fixture.league_avg_goals")
    if league is None:
        league = float(sc["league_avg_goals"])
    lo, hi = sc["league_avg_range"]
    if not lo <= league <= hi:
        raise PredictInputError(f"fixture.league_avg_goals={league} outside [{lo}, {hi}]: it must be goals per TEAM "
                                "per match (half the total goals per match)")
    ha = fx.take("fixture.home_advantage")
    if ha is None:
        ha = float(sc["home_advantage"])
    lo, hi = sc["home_advantage_range"]
    if not lo <= ha <= hi:
        raise PredictInputError(f"fixture.home_advantage={ha} outside [{lo}, {hi}] (a ratio, e.g. 1.2)")

    s = math.sqrt(ha)
    base = {"home": league * s, "away": league / s}
    w = float(sc["xg_weight"])
    ratings: dict[str, float] = {}
    for metric, spec in METRICS.items():
        side = SIDE[metric]
        key, v = fx.first(spec["goals"])
        r = v / (base[side] if key == spec["goals"][0] else league)
        xg = fx.first(spec["xg"]) if w > 0 else None
        if xg is not None:
            xkey, xv = xg
            rx = xv / (base[side] if xkey == spec["xg"][0] else league)
            r = (1 - w) * r + w * rx
        ratings[metric] = r

    floor = float(mc["lambda_floor"])
    lam_home = max(base["home"] * ratings["attack_H"] * ratings["defence_A"], floor)
    lam_away = max(base["away"] * ratings["attack_A"] * ratings["defence_H"], floor)
    return Strengths(lam_home, lam_away, league, ha, ratings, fx.used)
