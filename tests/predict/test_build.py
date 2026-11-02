"""build_prediction / write_prediction on a project folder: schema-valid, rule-clean, deterministic, provenance."""
from __future__ import annotations

import pytest

from tms import jsonio, schema
from tms.predict import PredictInputError, config
from tms.predict import build as BLD
from tms.validate import validate_file
from tests.helpers import place
from tests.predict._util import fact

pytestmark = pytest.mark.fast


@pytest.fixture
def project(tmp_path, dossier, analysis):
    d = tmp_path / "fx-match"
    place(d, "match_dossier", dossier)
    place(d, "match_analysis", analysis)
    return d


def test_build_is_schema_valid_and_rule_clean(project):
    doc = BLD.write_prediction(project)
    assert schema.validate_artifact("prediction", doc) == []
    assert validate_file(project, "prediction", "match_preview") == []
    on_disk = jsonio.read_json(project / "build" / "prediction.json")
    assert on_disk == doc
    assert doc["inputs"] == {"match_dossier": jsonio.sha256_file(project / "build" / "match_dossier.json"),
                             "match_analysis": jsonio.sha256_file(project / "artifacts" / "match_analysis.json")}


def test_build_is_deterministic_and_writes_nothing(project):
    a = BLD.build_prediction(project)
    assert not (project / "build" / "prediction.json").exists()
    assert BLD.build_prediction(project) == a


def test_headline_and_disclaimer(project):
    doc = BLD.build_prediction(project)
    pf = doc["probs_final"]
    assert doc["headline"]["result"] == max(pf, key=pf.get)
    hg, ag = map(int, doc["headline"]["scoreline"].split("-"))
    assert (hg > ag) if doc["headline"]["result"] == "home" else (hg < ag) if doc["headline"]["result"] == "away" \
        else hg == ag
    assert "not betting advice" in doc["disclaimer"].lower()
    # market odds are blended only when present; adjustments then move the blend within PR-03/PR-07 bounds
    assert (doc["odds_implied"] is None) == (doc["blend_weight"] == 0)
    if doc["odds_implied"] is None and not doc["adjustments_applied"]:
        assert doc["probs_final"] == doc["probs_model"]


def test_odds_and_adjustments_flow_through(project, dossier, analysis):
    for k, v in (("fixture.odds_home", 2.1), ("fixture.odds_draw", 3.6), ("fixture.odds_away", 3.4)):
        dossier["facts"][k] = fact(v, "agreed")
    analysis["prediction_adjustments"] = [
        {"outcome": "away", "delta_pp": -3, "reason": "Arsenal's first-choice striker is ruled out.", "refs": ["C-002"]}]
    place(project, "match_dossier", dossier)
    place(project, "match_analysis", analysis)
    doc = BLD.write_prediction(project)
    assert doc["blend_weight"] == config()["market"]["blend_weight"]
    assert doc["odds_implied"] is not None
    assert {"fixture.odds_home", "fixture.odds_draw", "fixture.odds_away"} <= {i["fact_key"] for i in doc["inputs_used"]}
    assert doc["adjustments_applied"] == analysis["prediction_adjustments"]
    w = doc["blend_weight"]
    blended_away = (1 - w) * doc["probs_model"]["away"] + w * doc["odds_implied"]["away"]
    assert doc["probs_final"]["away"] == pytest.approx(blended_away - 0.03, abs=2e-4)
    assert validate_file(project, "prediction", "match_preview") == []


def test_excessive_combined_adjustments_are_flagged_by_PR07(project, analysis):
    analysis["prediction_adjustments"] = [
        {"outcome": "home", "delta_pp": 10, "reason": "Home side unbeaten in twenty at this ground.", "refs": ["C-001"]},
        {"outcome": "home", "delta_pp": 10, "reason": "Away side travel after a midweek extra-time tie.", "refs": ["C-002"]}]
    place(project, "match_analysis", analysis)
    BLD.write_prediction(project)
    assert {f.rule for f in validate_file(project, "prediction", "match_preview")} == {"PR-07"}


def test_missing_inputs_explained(tmp_path, dossier):
    d = tmp_path / "fx-match"
    with pytest.raises(PredictInputError, match="match_dossier.json not found"):
        BLD.build_prediction(d)
    place(d, "match_dossier", dossier)
    with pytest.raises(PredictInputError, match="match_analysis.json not found"):
        BLD.build_prediction(d)


def test_missing_required_facts_name_the_keys(project, dossier):
    for k in ("A.goals_against_avg", "A.away_goals_against_avg"):
        dossier["facts"].pop(k, None)
    place(project, "match_dossier", dossier)
    with pytest.raises(PredictInputError, match=r"A\.goals_against_avg \(or A\.away_goals_against_avg\)"):
        BLD.build_prediction(project)
