"""PR — prediction rules (build/prediction.json). Thresholds: config/rules.d/prediction.yaml + config/predict.yaml."""
from __future__ import annotations

import math
import re

from tms.predict import OUTCOMES
from tms.predict import config as predict_config
from tms.predict import model as M
from tms.validate.registry import rule


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _other(ctx, name: str, rel: str):
    """(doc, problem): the other artifact, or a problem message when a real project lacks it."""
    doc = ctx.other(name)
    if doc is None and ctx.project_dir is not None:
        return None, f"{rel} not found; cannot cross-check"
    return doc, None


@rule("PR-01")
def probabilities_sum_to_one(doc, ctx, p):
    for key in ("probs_final", "probs_model", "odds_implied"):
        probs = doc.get(key)
        if probs is None:
            continue
        s = sum(probs[o] for o in OUTCOMES)
        if abs(s - 1.0) > p["tol"]:
            yield key, f"{key} sums to {s:.4f}, not 1 +/- {p['tol']}"


@rule("PR-02")
def inputs_used_match_dossier(doc, ctx, p):
    dossier, problem = _other(ctx, "match_dossier", "build/match_dossier.json")
    if problem:
        yield "inputs_used", problem
    if dossier is None:
        return
    facts = dossier.get("facts", {})
    for i, item in enumerate(doc["inputs_used"]):
        key, v = item["fact_key"], item["value"]
        fact = facts.get(key)
        loc = f"inputs_used/{i}"
        if fact is None:
            yield loc, f"{key} is not a fact in match_dossier"
            continue
        if fact.get("status") == "conflict":
            yield loc, f"{key} has an unresolved conflict in match_dossier and cannot feed the model"
        fv = fact.get("value")
        if not _number(fv) or not math.isclose(float(fv), float(v), rel_tol=p["rel_tol"], abs_tol=1e-12):
            yield loc, f"{key}: used value {v!r} != dossier value {fv!r}"


@rule("PR-03")
def adjustments_bounded_and_justified(doc, ctx, p):
    adj = doc["adjustments_applied"]
    for i, a in enumerate(adj):
        loc = f"adjustments_applied/{i}"
        if abs(a["delta_pp"]) > p["max_abs_delta_pp"]:
            yield loc, f"|delta_pp| = {abs(a['delta_pp'])} > {p['max_abs_delta_pp']}"
        if len(a["reason"].strip()) < p["min_reason"]:
            yield loc, f"adjustment needs a reason (>= {p['min_reason']} chars)"
        if not [r for r in a["refs"] if r.strip()]:
            yield loc, "adjustment must cite at least one dossier fact key or claim id in refs"
    analysis, problem = _other(ctx, "match_analysis", "artifacts/match_analysis.json")
    if problem:
        yield "adjustments_applied", problem
    if analysis is not None and adj != analysis.get("prediction_adjustments"):
        yield "adjustments_applied", ("adjustments_applied differs from match_analysis.prediction_adjustments "
                                      "(rebuild with `tms predict build`)")


@rule("PR-04")
def headline_consistent(doc, ctx, p):
    probs, head = doc["probs_final"], doc["headline"]
    best = M.argmax_outcome(probs)
    if head["result"] != best:
        yield "headline/result", f"headline result {head['result']} but the most likely outcome is {best}"
    hg, ag = (int(x) for x in re.match(r"^(\d+)-(\d+)$", head["scoreline"]).groups())
    if M.result_of(hg, ag) != head["result"]:
        yield "headline/scoreline", f"{head['scoreline']} is not a {head['result']} result"
    lines = doc["scorelines"]
    mine = [s for s in lines if (s["home"], s["away"]) == (hg, ag)]
    if not mine:
        yield "headline/scoreline", f"{head['scoreline']} is not among the listed scorelines"
        return
    pm = mine[0]["p"]
    ranked = sorted((s["p"] for s in lines), reverse=True)
    kth = ranked[min(p["top_k"], len(ranked)) - 1]
    if pm < kth - 1e-12:
        yield "headline/scoreline", f"{head['scoreline']} (p={pm}) is not among the top-{p['top_k']} scorelines"
    same = [s["p"] for s in lines if M.result_of(s["home"], s["away"]) == head["result"]]
    if pm < max(same) - 1e-12:
        yield "headline/scoreline", f"{head['scoreline']} is not the most likely listed {head['result']} scoreline"


@rule("PR-05")
def confidence_matches_entropy(doc, ctx, p):
    probs = doc["probs_final"]
    h = M.entropy(probs)
    if abs(h - doc["entropy"]) > p["entropy_tol"]:
        yield "entropy", f"entropy {doc['entropy']} but H(probs_final) = {h:.4f} nats"
    want = M.confidence_from(h, M.margin(probs), predict_config()["confidence"])
    if doc["confidence"] != want:
        yield "confidence", (f"confidence {doc['confidence']!r} but entropy {h:.3f} / margin {M.margin(probs):.3f} "
                             f"give {want!r} (thresholds: config/predict.yaml confidence)")


@rule("PR-06")
def disclaimer_not_betting_advice(doc, ctx, p):
    if p["phrase"].lower() not in " ".join(doc["disclaimer"].split()).lower():
        yield "disclaimer", f"disclaimer must say {p['phrase']!r}"


@rule("PR-07")
def bounded_drift_from_blend(doc, ctx, p):
    w, model, odds, final = doc["blend_weight"], doc["probs_model"], doc["odds_implied"], doc["probs_final"]
    if odds is None and w != 0:
        yield "blend_weight", f"blend_weight {w} without odds_implied (must be 0)"
    if w > p["max_blend_weight"]:
        yield "blend_weight", f"blend_weight {w} > {p['max_blend_weight']}"
    blended = {o: model[o] if odds is None else (1 - w) * model[o] + w * odds[o] for o in OUTCOMES}
    for o in OUTCOMES:
        drift = abs(final[o] - blended[o]) * 100
        if drift > p["max_drift_pp"] + 1e-9:
            yield f"probs_final/{o}", (f"{o} moved {drift:.1f} pp from the model/market blend "
                                       f"({blended[o]:.3f} -> {final[o]:.3f}); combined adjustments may move an "
                                       f"outcome at most {p['max_drift_pp']} pp")
