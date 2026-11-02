"""`tms render final` — build render_props, render, mix, mux, check (FQ), write render_report."""
from __future__ import annotations

from tms import validate as V
from tms.commands.common import add_project_arg, handled
from tms.render.stage import run_final, summary
from tms.state import machine, project as P


@handled
def cmd_final(a):
    pr = P.load(a.project)
    machine.require_active(pr, "render")
    report = run_final(pr, scale=a.scale)
    print(summary(report))
    findings = V.validate_file(pr.dir, "render_props", pr.mode) + V.validate_file(pr.dir, "render_report", pr.mode)
    for f in findings:
        print(f"  {f.severity.upper():7s} [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}")
    print(f"QA frames for visual-qa: projects/{pr.id}/renders/qa/  contact sheet: projects/{pr.id}/renders/final_contact_sheet.png")
    return 1 if report["verdict"] != "pass" or V.errors_only(findings) else 0


def register(sub) -> None:
    p = sub.add_parser("render", help="final render for the render stage")
    rsub = p.add_subparsers(dest="render_action", required=True)
    f = rsub.add_parser("final", help="render_props -> final.mp4 + captions.srt + render_report (FQ checks)")
    add_project_arg(f)
    f.add_argument("--scale", type=float, default=1.0, help="1.0 = 1920x1080 (16:9); 0.5 for quick previews")
    f.set_defaults(func=cmd_final)
