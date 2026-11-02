"""`tms predict build|backtest` (registered on a fresh parser; tms.cli wiring is done separately)."""
from __future__ import annotations

import argparse
import json

import pytest

from tms import cli as tms_cli
from tms import jsonio
from tms.predict import backtest as BT
from tms.predict import cli as pcli
from tms.state import project as P
from tests.helpers import place

pytestmark = pytest.mark.fast


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="tms")
    pcli.register(parser.add_subparsers(dest="command", required=True))
    a = parser.parse_args(argv)
    return a.func(a)


def test_build_refused_when_analysis_stage_not_active(tmp_projects, capsys, dossier, analysis):
    pr = P.init("rma-ars", "match_preview", "Real Madrid v Arsenal", True)
    place(pr.dir, "match_dossier", dossier)
    place(pr.dir, "match_analysis", analysis)
    assert run(["predict", "build", "-p", "rma-ars"]) == 2
    err = capsys.readouterr().err
    assert "GATE:" in err and "analysis" in err
    assert not (pr.dir / "build" / "prediction.json").exists()


def test_build_refused_through_tms_cli_wiring(tmp_projects, monkeypatch, capsys):
    assert "tms.predict.cli" in tms_cli.COMMAND_MODULES  # wired into the real CLI
    P.init("rma-ars", "match_preview", "Real Madrid v Arsenal", True)
    assert tms_cli.main(["predict", "build", "-p", "rma-ars"]) == 2
    assert "GATE:" in capsys.readouterr().err


def test_build_in_tactic_mode_is_an_error(tmp_projects, capsys):
    P.init("ifb-442", "tactic", "4-4-2 press", True)
    assert run(["predict", "build", "-p", "ifb-442"]) == 1
    assert "not part of mode tactic" in capsys.readouterr().err


def test_build_writes_prediction_when_stage_active(tmp_projects, monkeypatch, capsys, dossier, analysis):
    pr = P.init("rma-ars", "match_preview", "Real Madrid v Arsenal", True)
    place(pr.dir, "match_dossier", dossier)
    place(pr.dir, "match_analysis", analysis)
    calls = []
    monkeypatch.setattr(pcli.machine, "require_active", lambda project, stage: calls.append((project.id, stage)))
    assert run(["predict", "build", "-p", "rma-ars", "--json"]) == 0
    assert calls == [("rma-ars", "analysis")]
    out = json.loads(capsys.readouterr().out)
    assert out["findings"] == []
    assert jsonio.read_json(pr.dir / "build" / "prediction.json") == out["prediction"]
    assert out["prediction"]["project_id"] == "rma-ars"


def test_build_missing_facts_exit_1(tmp_projects, monkeypatch, capsys, dossier, analysis):
    pr = P.init("rma-ars", "match_preview", "Real Madrid v Arsenal", True)
    for k in [k for k in dossier["facts"] if k.startswith("H.") and "goals_against" in k]:
        del dossier["facts"][k]  # overall AND venue-split figures: the model cannot rate Madrid's defence
    place(pr.dir, "match_dossier", dossier)
    place(pr.dir, "match_analysis", analysis)
    monkeypatch.setattr(pcli.machine, "require_active", lambda project, stage: None)
    assert run(["predict", "build", "-p", "rma-ars"]) == 1
    assert "H.goals_against_avg" in capsys.readouterr().err


def test_backtest_prints_json_report(tmp_path, capsys):
    p = tmp_path / "season.csv"
    BT.write_csv(p, BT.generate_season(20, seed=7)[0])
    assert run(["predict", "backtest", "--csv", str(p), "--warmup", "100"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["csv"] == "season.csv" and rep["evaluated"] == 280
    assert rep["model"]["brier"] < rep["baseline"]["brier"]


def test_backtest_missing_csv_exit_1(tmp_path, capsys):
    assert run(["predict", "backtest", "--csv", str(tmp_path / "nope.csv")]) == 1
    assert "CSV not found" in capsys.readouterr().err
