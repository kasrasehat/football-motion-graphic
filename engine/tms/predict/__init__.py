"""Match prediction: Dixon-Coles goals model fed by dossier facts, optional market blend, bounded analyst adjustments.

    strengths.py  dossier facts -> expected goals (lambda home / away) + the facts actually used
    model.py      Dixon-Coles score matrix -> outcome probabilities, scorelines, entropy, confidence
    blend.py      market odds de-vig + blend, analyst adjustments (bounded, clipped, renormalised)
    build.py      build/prediction.json from build/match_dossier.json + artifacts/match_analysis.json
    backtest.py   rolling-origin maximum-likelihood evaluation on historical results (Brier / log-loss)
    cli.py        `tms predict build|backtest`

Parameters live in config/predict.yaml; the method in plain language is skills/prediction-model/SKILL.md.
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from tms import paths

OUTCOMES = ("home", "draw", "away")


class PredictInputError(ValueError):
    """The dossier/analysis cannot feed the model (missing or implausible facts). User-facing message."""

    def __init__(self, message: str, missing: list[str] | None = None):
        super().__init__(message)
        self.missing = list(missing or [])


@lru_cache(maxsize=1)
def config() -> dict:
    """config/predict.yaml (cached). Callers must not mutate the returned dict."""
    return yaml.safe_load((paths.config_dir() / "predict.yaml").read_text(encoding="utf-8"))
