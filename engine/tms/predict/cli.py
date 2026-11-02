"""`tms predict build|backtest` — wire with tms.cli.COMMAND_MODULES += ["tms.predict.cli"]."""
from __future__ import annotations

import json
import sys

from tms.commands.common import add_project_arg, emit, handled
from tms.predict import OUTCOMES, PredictInputError
from tms.state import machine, project as P
from tms.state.project import ProjectError

STAGE = "analysis"


@handled
def cmd_build(a):
    from tms import validate as V
    from tms.predict import build
    from tms.validate.registry import Context

    pr = P.load(a.project)
    machine.require_active(pr, STAGE)  # GateViolation -> exit 2 unless the analysis stage is in progress/stale
    try:
        doc = build.write_prediction(pr.dir)
    except PredictInputError as e:
        raise ProjectError(str(e)) from e
    findings = V.validate_doc("prediction", doc, Context(project_dir=pr.dir, mode=pr.mode))
    errors = [f for f in findings if f.severity == "error"]
    pf = doc["probs_final"]
    text = (f"wrote build/prediction.json  lambda {doc['lambda']['home']:.2f}-{doc['lambda']['away']:.2f}  "
            + "  ".join(f"{o} {pf[o] * 100:.1f}%" for o in OUTCOMES)
            + f"  headline {doc['headline']['result']} {doc['headline']['scoreline']}  confidence {doc['confidence']}"
            + f"\n  inputs_used: {', '.join(i['fact_key'] for i in doc['inputs_used'])}")
    emit({"prediction": doc, "findings": [f.as_dict() for f in findings]}, a.json, text)
    for f in findings:
        print(f"  [{f.rule}] {f.severity}: {f.location + ': ' if f.location else ''}{f.message}", file=sys.stderr)
    return 1 if errors else 0


@handled
def cmd_backtest(a):
    from tms.predict import backtest

    try:
        report = backtest.run_csv(a.csv, a.warmup)
    except PredictInputError as e:
        raise ProjectError(str(e)) from e
    print(json.dumps(report, indent=2))
    return 0


def register(sub) -> None:
    p = sub.add_parser("predict", help="match prediction model (Dixon-Coles): build prediction.json, backtest")
    ps = p.add_subparsers(dest="predict_command", required=True)

    b = ps.add_parser("build", help="compute build/prediction.json from match_dossier + match_analysis "
                                    "(only while the analysis stage is active)")
    add_project_arg(b)
    b.add_argument("--json", action="store_true", help="print the prediction and findings as JSON")
    b.set_defaults(func=cmd_build)

    t = ps.add_parser("backtest", help="rolling-origin backtest (Brier, log-loss vs base rates) on a results CSV")
    t.add_argument("--csv", required=True, metavar="FILE", help="columns: date,home,away,home_goals,away_goals")
    t.add_argument("--warmup", type=int, default=None, metavar="N",
                   help="earlier matches required before a match is scored (default: config/predict.yaml)")
    t.set_defaults(func=cmd_backtest)
