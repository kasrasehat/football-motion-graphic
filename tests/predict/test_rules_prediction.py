"""PR rules: the fixture is clean; each mutation triggers the intended rule."""
from __future__ import annotations

import pytest

from tms import paths
from tms.predict import config as predict_config
from tms.validate.registry import Context, params
from tests.helpers import expect_clean, expect_violation, fixture

pytestmark = pytest.mark.fast


def ctx() -> Context:
    return Context(artifacts={"match_dossier": fixture("match_dossier"), "match_analysis": fixture("match_analysis")})


ADJ = {"outcome": "home", "delta_pp": 4, "reason": "Arsenal's first-choice centre-back is suspended.", "refs": ["C-002"]}


def test_fixture_clean():
    expect_clean("prediction", fixture("prediction"))
    expect_clean("prediction", fixture("prediction"), ctx())


def test_PR01_final_probs_do_not_sum_to_one():
    d = fixture("prediction")
    d["probs_final"]["home"] = 0.5
    expect_violation("PR-01", "prediction", d)


def test_PR01_odds_implied_do_not_sum_to_one():
    d = fixture("prediction")
    d["odds_implied"] = {"home": 0.5, "draw": 0.3, "away": 0.25}
    expect_violation("PR-01", "prediction", d)


def test_PR02_value_differs_from_dossier():
    d = fixture("prediction")
    d["inputs_used"][0]["value"] = 2.4
    expect_violation("PR-02", "prediction", d, ctx())


def test_PR02_unknown_fact_key():
    d = fixture("prediction")
    d["inputs_used"].append({"fact_key": "A.xg_against_avg", "value": 1.3})
    expect_violation("PR-02", "prediction", d, ctx())


def test_PR02_conflicted_fact():
    c = ctx()
    used = fixture("prediction")["inputs_used"][0]["fact_key"]  # a fact the model actually consumed
    c.artifacts["match_dossier"]["facts"][used]["status"] = "conflict"
    expect_violation("PR-02", "prediction", fixture("prediction"), c)


def test_PR02_dossier_missing_in_project(tmp_path):
    expect_violation("PR-02", "prediction", fixture("prediction"), Context(project_dir=tmp_path / "fx-match"))


def test_PR03_delta_out_of_bounds():
    d = fixture("prediction")
    d["adjustments_applied"] = [{**ADJ, "delta_pp": 12}]
    expect_violation("PR-03", "prediction", d)


def test_PR03_adjustment_without_refs_or_reason():
    d = fixture("prediction")
    d["adjustments_applied"] = [{**ADJ, "refs": []}]
    expect_violation("PR-03", "prediction", d)
    d["adjustments_applied"] = [{**ADJ, "reason": "gut"}]
    expect_violation("PR-03", "prediction", d)


def test_PR03_adjustments_differ_from_match_analysis():
    d = fixture("prediction")
    d["adjustments_applied"] = [ADJ]  # match_analysis fixture has none
    expect_violation("PR-03", "prediction", d, ctx())


def test_PR04_headline_result_not_argmax():
    d = fixture("prediction")
    d["headline"] = {"result": "away", "scoreline": "0-1"}
    expect_violation("PR-04", "prediction", d)


def test_PR04_scoreline_inconsistent_with_result():
    d = fixture("prediction")
    d["headline"]["scoreline"] = "1-1"
    expect_violation("PR-04", "prediction", d)


def test_PR04_scoreline_not_most_likely_of_its_result():
    d = fixture("prediction")
    d["headline"]["scoreline"] = "2-1"  # 1-0 is the likelier home score
    expect_violation("PR-04", "prediction", d)


def test_PR04_scoreline_not_in_top3():
    d = fixture("prediction")
    d["scorelines"] = [{"home": 1, "away": 1, "p": 0.11}, {"home": 0, "away": 0, "p": 0.10},
                       {"home": 0, "away": 1, "p": 0.098}, {"home": 2, "away": 1, "p": 0.095}]
    expect_violation("PR-04", "prediction", d)


def test_PR04_scoreline_not_listed():
    d = fixture("prediction")
    d["headline"]["scoreline"] = "3-0"
    expect_violation("PR-04", "prediction", d)


def test_PR05_label_inconsistent_with_entropy():
    d = fixture("prediction")
    d["confidence"] = "high"
    expect_violation("PR-05", "prediction", d)


def test_PR05_entropy_misreported():
    d = fixture("prediction")
    d["entropy"] = 0.8
    expect_violation("PR-05", "prediction", d)


def test_PR06_disclaimer_without_phrase():
    d = fixture("prediction")
    d["disclaimer"] = "Statistical analysis for entertainment purposes only."
    expect_violation("PR-06", "prediction", d)


def test_PR07_final_drifts_too_far_from_model():
    d = fixture("prediction")
    d["probs_final"] = {"home": 0.67, "draw": 0.14, "away": 0.19}
    expect_violation("PR-07", "prediction", d)


def test_PR07_blend_weight_without_odds():
    d = fixture("prediction")
    d["odds_implied"] = None  # the fixture blends market odds; without them any blend weight is invalid
    d["blend_weight"] = 0.2
    expect_violation("PR-07", "prediction", d)


def test_PR07_drift_measured_from_market_blend():
    d = fixture("prediction")
    d["odds_implied"] = {"home": 0.37, "draw": 0.28, "away": 0.35}
    d["blend_weight"] = 0.35  # blend: home 0.435, draw 0.254, away 0.311 -> final == model is within bounds
    expect_clean("prediction", d)
    d["blend_weight"] = 0.6
    expect_violation("PR-07", "prediction", d)


def test_rule_params_agree_with_engine_config():
    cfg = predict_config()
    assert params("PR-03")["max_abs_delta_pp"] == cfg["adjustments"]["max_abs_delta_pp"]
    assert cfg["market"]["blend_weight"] <= params("PR-07")["max_blend_weight"]
    assert params("PR-06")["phrase"] in " ".join(cfg["disclaimer"].split()).lower()
    analysis_schema = (paths.schemas_dir() / "artifacts" / "match_analysis.schema.json").read_text(encoding="utf-8")
    assert '"delta_pp": {"type": "number", "minimum": -10, "maximum": 10}' in analysis_schema
