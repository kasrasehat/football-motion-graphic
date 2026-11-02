"""Rolling-origin backtest of the Dixon-Coles model on historical results.

CSV columns: date,home,away,home_goals,away_goals (date = YYYY-MM-DD). For every match date D with at least `warmup`
earlier matches, the model is refitted on matches strictly before D and predicts every match on D. Fit = weighted
maximum likelihood (L-BFGS-B, analytic gradient, fixed iteration cap, deterministic cold start):

    log lambda_k = c + g + a[home_k] + d[away_k]          log mu_k = c + a[away_k] + d[home_k]
    NLL = -sum_k w_k [log tau_k + x_k log lambda_k - lambda_k + y_k log mu_k - mu_k]  +  ridge * (|a|^2 + |d|^2)
    w_k = 2^(-(D - date_k) / half_life_days), normalised to sum 1;  rho bounded to backtest.rho_bounds

Scores: multiclass Brier sum_o (p_o - y_o)^2 (0 = perfect, 2 = worst) and log-loss -ln p(actual), against a baseline
that predicts the league-wide home/draw/away frequencies of the same earlier window (add-one smoothed).
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

from tms.predict import OUTCOMES, PredictInputError, config
from tms.predict import model as M

COLUMNS = ("date", "home", "away", "home_goals", "away_goals")


@dataclass(frozen=True)
class Match:
    date: date
    home: str
    away: str
    home_goals: int
    away_goals: int

    @property
    def result(self) -> str:
        return M.result_of(self.home_goals, self.away_goals)


# ----------------------------------------------------------------------------- CSV I/O
def read_csv(path: Path) -> list[Match]:
    path = Path(path)
    if not path.is_file():
        raise PredictInputError(f"CSV not found: {path}")
    out: list[Match] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = [c.strip() for c in (reader.fieldnames or [])]
        if any(c not in cols for c in COLUMNS):
            raise PredictInputError(f"{path.name}: header must contain {','.join(COLUMNS)} (got {','.join(cols)})")
        for n, row in enumerate(reader, 2):
            # extra unnamed fields (key None, list value) are ignored; missing fields arrive as None
            row = {k.strip(): (v or "").strip() for k, v in row.items() if isinstance(k, str) and not isinstance(v, list)}
            try:
                m = Match(date.fromisoformat(row["date"]), row["home"], row["away"],
                          int(row["home_goals"]), int(row["away_goals"]))
            except ValueError as e:
                raise PredictInputError(f"{path.name} line {n}: {e}") from e
            if not m.home or not m.away or m.home == m.away or m.home_goals < 0 or m.away_goals < 0:
                raise PredictInputError(f"{path.name} line {n}: bad match row {row}")
            out.append(m)
    if not out:
        raise PredictInputError(f"{path.name}: no matches")
    return sorted(out, key=lambda m: m.date)  # stable: same-day order kept


def write_csv(path: Path, matches: Sequence[Match]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for m in matches:
            w.writerow([m.date.isoformat(), m.home, m.away, m.home_goals, m.away_goals])


# ----------------------------------------------------------------------------- synthetic season
def generate_season(n_teams: int = 20, seed: int = 7, *, start: str = "2025-08-09", base_goals: float = 1.10,
                    home_advantage: float = 1.30, rho: float = -0.10, attack_sd: float = 0.35,
                    defence_sd: float = 0.30, max_goals: int = 10) -> tuple[list[Match], dict]:
    """Seeded double round-robin (n_teams*(n_teams-1) matches, one round per week) with known true strengths.

    Truth uses the backtest parametrisation: lambda = base * HA * exp(a_home + d_away), mu = base * exp(a_away + d_home).
    """
    if n_teams < 2 or n_teams % 2:
        raise ValueError("n_teams must be even and >= 2")
    rng = np.random.default_rng(seed)
    teams = [f"Team {k + 1:02d}" for k in range(n_teams)]
    att = rng.normal(0.0, attack_sd, n_teams)
    dfn = rng.normal(0.0, defence_sd, n_teams)
    att -= att.mean()
    dfn -= dfn.mean()
    # circle method: team 0 fixed, others rotate; alternate home/away of the fixed pairing for balance
    rot = list(range(n_teams))
    first_half: list[list[tuple[int, int]]] = []
    for r in range(n_teams - 1):
        pairs = []
        for k in range(n_teams // 2):
            h, a = rot[k], rot[n_teams - 1 - k]
            pairs.append((h, a) if (r + k) % 2 == 0 else (a, h))
        first_half.append(pairs)
        rot = [rot[0], rot[-1], *rot[1:-1]]
    rounds = first_half + [[(a, h) for h, a in pairs] for pairs in first_half]
    d0 = date.fromisoformat(start)
    matches: list[Match] = []
    for r, pairs in enumerate(rounds):
        day = d0 + timedelta(days=7 * r)
        for h, a in pairs:
            lam = base_goals * home_advantage * math.exp(att[h] + dfn[a])
            mu = base_goals * math.exp(att[a] + dfn[h])
            mat = M.score_matrix(lam, mu, rho, max_goals)
            idx = int(rng.choice(mat.size, p=mat.ravel()))
            hg, ag = divmod(idx, max_goals + 1)
            matches.append(Match(day, teams[h], teams[a], hg, ag))
    truth = {"teams": teams, "attack": dict(zip(teams, att.tolist())), "defence": dict(zip(teams, dfn.tolist())),
             "base_goals": base_goals, "home_advantage": home_advantage, "rho": rho}
    return matches, truth


# ----------------------------------------------------------------------------- model fit
@dataclass
class Fit:
    teams: list[str]
    c: float
    g: float
    rho: float
    attack: np.ndarray
    defence: np.ndarray
    converged: bool
    iterations: int

    def lambdas(self, home: str, away: str) -> tuple[float, float]:
        i, j = self.teams.index(home), self.teams.index(away)
        return (math.exp(self.c + self.g + self.attack[i] + self.defence[j]),
                math.exp(self.c + self.attack[j] + self.defence[i]))

    def probs(self, home: str, away: str, max_goals: int = 10) -> dict[str, float]:
        lam, mu = self.lambdas(home, away)
        return M.outcome_probs(M.score_matrix(lam, mu, self.rho, max_goals))


def _nll_and_grad(theta: np.ndarray, hi: np.ndarray, ai: np.ndarray, x: np.ndarray, y: np.ndarray,
                  w: np.ndarray, n: int, ridge: float) -> tuple[float, np.ndarray]:
    c, g, rho = theta[0], theta[1], theta[2]
    a, d = theta[3:3 + n], theta[3 + n:3 + 2 * n]
    lam = np.exp(c + g + a[hi] + d[ai])
    mu = np.exp(c + a[ai] + d[hi])
    z00, z01, z10, z11 = (x == 0) & (y == 0), (x == 0) & (y == 1), (x == 1) & (y == 0), (x == 1) & (y == 1)
    tau = np.ones_like(lam)
    tau = np.where(z00, 1 - lam * mu * rho, tau)
    tau = np.where(z01, 1 + lam * rho, tau)
    tau = np.where(z10, 1 + mu * rho, tau)
    tau = np.where(z11, 1 - rho, tau)
    tau = np.maximum(tau, 1e-10)
    ll = np.log(tau) + x * np.log(lam) - lam + y * np.log(mu) - mu
    nll = -float(np.sum(w * ll)) + ridge * float(a @ a + d @ d)

    dtau_dlam = np.where(z00, -mu * rho, 0.0) + np.where(z01, rho, 0.0)
    dtau_dmu = np.where(z00, -lam * rho, 0.0) + np.where(z10, rho, 0.0)
    dtau_drho = np.where(z00, -lam * mu, 0.0) + np.where(z01, lam, 0.0) + np.where(z10, mu, 0.0) - z11.astype(float)
    gl = -w * (x - lam + lam * dtau_dlam / tau)   # dNLL / dlog(lambda_k)
    gm = -w * (y - mu + mu * dtau_dmu / tau)      # dNLL / dlog(mu_k)
    grad = np.empty_like(theta)
    grad[0] = gl.sum() + gm.sum()
    grad[1] = gl.sum()
    grad[2] = -float(np.sum(w * dtau_drho / tau))
    grad[3:3 + n] = np.bincount(hi, gl, n) + np.bincount(ai, gm, n) + 2 * ridge * a
    grad[3 + n:3 + 2 * n] = np.bincount(ai, gl, n) + np.bincount(hi, gm, n) + 2 * ridge * d
    return nll, grad


def fit(matches: Sequence[Match], teams: list[str], as_of: date, cfg: Mapping[str, Any] | None = None) -> Fit:
    """Weighted MLE of (c, g, rho, attack, defence) on `matches` as seen on date `as_of`."""
    bc = (cfg or config())["backtest"]
    n = len(teams)
    idx = {t: k for k, t in enumerate(teams)}
    hi = np.array([idx[m.home] for m in matches], dtype=np.int64)
    ai = np.array([idx[m.away] for m in matches], dtype=np.int64)
    x = np.array([m.home_goals for m in matches], dtype=float)
    y = np.array([m.away_goals for m in matches], dtype=float)
    age = np.array([(as_of - m.date).days for m in matches], dtype=float)
    w = np.power(2.0, -age / float(bc["half_life_days"]))
    w = w / w.sum()
    mean_goals = max(float((x.sum() + y.sum()) / (2 * len(matches))), 0.1)
    theta0 = np.zeros(3 + 2 * n)
    theta0[0] = math.log(mean_goals)
    lo, hi_r = bc["rho_bounds"]
    bounds = [(None, None), (None, None), (float(lo), float(hi_r))] + [(None, None)] * (2 * n)
    res = minimize(_nll_and_grad, theta0, args=(hi, ai, x, y, w, n, float(bc["ridge"])), jac=True,
                   method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": int(bc["max_iter"]), "ftol": 1e-12, "gtol": 1e-8})
    t = res.x
    return Fit(list(teams), float(t[0]), float(t[1]), float(t[2]), t[3:3 + n].copy(), t[3 + n:].copy(),
               bool(res.success), int(res.nit))


# ----------------------------------------------------------------------------- evaluation
def brier(p: Mapping[str, float], actual: str) -> float:
    return float(sum((p[o] - (1.0 if o == actual else 0.0)) ** 2 for o in OUTCOMES))


def log_loss(p: Mapping[str, float], actual: str) -> float:
    return -math.log(max(p[actual], 1e-15))


def baseline_probs(window: Sequence[Match]) -> dict[str, float]:
    counts = {o: 1.0 for o in OUTCOMES}  # add-one smoothing
    for m in window:
        counts[m.result] += 1
    total = sum(counts.values())
    return {o: counts[o] / total for o in OUTCOMES}


def run(matches: Sequence[Match], warmup: int | None = None, cfg: Mapping[str, Any] | None = None,
        details: bool = False) -> dict:
    """Rolling-origin evaluation; details=True adds every scored prediction (date, teams, model and baseline probs)."""
    cfg = cfg or config()
    bc = cfg["backtest"]
    warmup = int(bc["warmup"] if warmup is None else warmup)
    if warmup < 1:
        raise PredictInputError("--warmup must be >= 1")
    matches = sorted(matches, key=lambda m: m.date)
    teams = sorted({m.home for m in matches} | {m.away for m in matches})
    max_goals = int(cfg["model"]["max_goals"])
    dates = sorted({m.date for m in matches})
    tot = {"model": [0.0, 0.0], "baseline": [0.0, 0.0]}
    evaluated = refits = 0
    last: Fit | None = None
    rows: list[dict] = []
    for day in dates:
        train = [m for m in matches if m.date < day]
        if len(train) < warmup:
            continue
        last = fit(train, teams, day, cfg)
        refits += 1
        base = baseline_probs(train)
        for m in (m for m in matches if m.date == day):
            pm = last.probs(m.home, m.away, max_goals)
            for key, p in (("model", pm), ("baseline", base)):
                tot[key][0] += brier(p, m.result)
                tot[key][1] += log_loss(p, m.result)
            evaluated += 1
            if details:
                rows.append({"date": m.date.isoformat(), "home": m.home, "away": m.away, "result": m.result,
                             "model": {o: round(pm[o], 6) for o in OUTCOMES},
                             "baseline": {o: round(base[o], 6) for o in OUTCOMES}})
    if evaluated == 0:
        raise PredictInputError(f"nothing to evaluate: {len(matches)} matches but warmup={warmup}")
    score = {k: {"brier": round(v[0] / evaluated, 6), "log_loss": round(v[1] / evaluated, 6)} for k, v in tot.items()}
    report = {
        "matches": len(matches), "teams": len(teams), "warmup": warmup, "evaluated": evaluated, "refits": refits,
        "model": score["model"], "baseline": score["baseline"],
        "brier_skill": round(1 - score["model"]["brier"] / score["baseline"]["brier"], 6),
        "beats_baseline": {"brier": score["model"]["brier"] < score["baseline"]["brier"],
                           "log_loss": score["model"]["log_loss"] < score["baseline"]["log_loss"]},
        "settings": {"half_life_days": bc["half_life_days"], "ridge": bc["ridge"], "rho_bounds": list(bc["rho_bounds"]),
                     "max_iter": bc["max_iter"], "max_goals": max_goals},
        "last_fit": {"home_advantage": round(math.exp(last.g), 4), "rho": round(last.rho, 4),
                     "base_goals": round(math.exp(last.c), 4), "converged": last.converged,
                     "iterations": last.iterations},
    }
    if details:
        report["predictions"] = rows
    return report


def run_csv(path: Path, warmup: int | None = None) -> dict:
    return {"csv": Path(path).name, **run(read_csv(path), warmup)}
