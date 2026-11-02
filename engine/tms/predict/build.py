"""build/prediction.json from build/match_dossier.json + artifacts/match_analysis.json (engine-built, never by hand).

Pipeline: strengths (lambdas) -> Dixon-Coles matrix -> probs_model -> market blend (if odds facts) -> analyst
adjustments -> probs_final. Scorelines are the model matrix rescaled so each result's total equals probs_final;
headline result = argmax(probs_final), headline scoreline = the most likely scoreline with that result.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from tms import jsonio, manifest, schema
from tms.predict import OUTCOMES, PredictInputError, config
from tms.predict import blend as B
from tms.predict import model as M
from tms.predict import strengths as S

ROUND_P = 4      # outcome probabilities, entropy
ROUND_SCORE = 6  # scoreline probabilities
ROUND_LAMBDA = 4


def _load(project_dir: Path, name: str, hint: str) -> tuple[dict, str]:
    p = manifest.artifact_path(project_dir, name)
    if not p.is_file():
        raise PredictInputError(f"{p.relative_to(project_dir).as_posix()} not found: {hint}")
    try:
        doc = jsonio.read_json(p)
    except ValueError as e:
        raise PredictInputError(f"{name}: invalid JSON ({e})") from e
    errs = schema.validate_artifact(name, doc)
    if errs:
        raise PredictInputError(f"{name} is not schema-valid; fix it first:\n  - " + "\n  - ".join(errs[:10]))
    return doc, jsonio.sha256_file(p)


def _project_id(project_dir: Path, dossier: Mapping[str, Any]) -> str:
    pj = Path(project_dir) / "project.json"
    if pj.is_file():
        return jsonio.read_json(pj)["project_id"]
    return dossier["project_id"]


def compute(dossier: Mapping[str, Any], analysis: Mapping[str, Any], cfg: Mapping[str, Any] | None = None) -> dict:
    """Everything except provenance: returns the prediction body (pure function of the two documents + config)."""
    cfg = cfg or config()
    mc = cfg["model"]
    facts = dossier["facts"]

    st = S.compute(facts, cfg)
    max_goals = int(mc["max_goals"])
    rho = M.effective_rho(st.lam_home, st.lam_away, float(mc["rho"]))
    matrix = M.score_matrix(st.lam_home, st.lam_away, rho, max_goals)
    p_model = M.outcome_probs(matrix)

    odds, odds_used = B.odds_from_facts(facts)
    market = B.implied_from_odds(odds) if odds is not None else None
    weight = float(cfg["market"]["blend_weight"]) if market is not None else 0.0
    blended = B.blend(p_model, market, weight)
    p_final, applied = B.apply_adjustments(blended, analysis.get("prediction_adjustments", []), cfg)

    probs_final = M.round_probs(p_final, ROUND_P)
    final_matrix = M.reweight_to(matrix, p_final)
    result = M.argmax_outcome(probs_final)
    hg, ag = M.best_scoreline_for(final_matrix, result)
    scorelines = [{**s, "p": round(s["p"], ROUND_SCORE)} for s in M.top_scorelines(final_matrix, int(mc["top_scorelines"]))]
    h = M.entropy(probs_final)

    inputs_used = [{"fact_key": k, "value": v} for k, v in [*st.inputs_used, *odds_used]]
    return {
        "model": {"name": "dixon-coles", "home_advantage": round(st.home_advantage, 4), "rho": round(rho, 4),
                  "league_avg_goals": round(st.league_avg, 4), "max_goals": max_goals},
        "inputs_used": inputs_used,
        "lambda": {"home": round(st.lam_home, ROUND_LAMBDA), "away": round(st.lam_away, ROUND_LAMBDA)},
        "probs_model": M.round_probs(p_model, ROUND_P),
        "odds_implied": M.round_probs(market, ROUND_P) if market is not None else None,
        "blend_weight": weight,
        "adjustments_applied": applied,
        "probs_final": probs_final,
        "scorelines": scorelines,
        "headline": {"result": result, "scoreline": f"{hg}-{ag}"},
        "confidence": M.confidence_label(probs_final, cfg["confidence"]),
        "entropy": round(h, ROUND_P),
        "disclaimer": " ".join(str(cfg["disclaimer"]).split()),
    }


def build_prediction(project_dir: Path) -> dict:
    """Read the dossier + analysis of a project and return a schema-valid prediction (writes nothing)."""
    project_dir = Path(project_dir)
    dossier, h_dossier = _load(project_dir, "match_dossier", "run the research stage first")
    analysis, h_analysis = _load(project_dir, "match_analysis",
                                 "write the analysis first (prediction_adjustments may be an empty list)")
    body = compute(dossier, analysis)
    doc = {"version": "1", "project_id": _project_id(project_dir, dossier),
           "inputs": {"match_dossier": h_dossier, "match_analysis": h_analysis}, **body}
    errs = schema.validate_artifact("prediction", doc)
    if errs:  # an engine bug, never user error
        raise RuntimeError("internal: built prediction is not schema-valid: " + "; ".join(errs))
    return doc


def write_prediction(project_dir: Path) -> dict:
    doc = build_prediction(project_dir)
    jsonio.write_json(manifest.artifact_path(Path(project_dir), "prediction"), doc)
    return doc


__all__ = ["OUTCOMES", "build_prediction", "compute", "write_prediction"]
