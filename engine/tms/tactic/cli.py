"""`tms tactic …` commands: templates, scaffold, zones."""
from __future__ import annotations

import json
from pathlib import Path

from tms import jsonio
from tms.commands.common import handled
from tms.state.project import ProjectError
from tms.tactic import formations as F
from tms.tactic.geometry import ZONES
from tms.tactic.scaffold import scaffold


@handled
def cmd_templates(a):
    for name in F.template_names():
        t = F.template(name)
        roles = " ".join(p["role"] for p in sorted(t["players"], key=lambda p: (p["line"], p["v"])))
        print(f"{name:10s} lines {t['formation']:10s} GK {roles}")


@handled
def cmd_zones(a):
    for name, (x, y) in sorted(ZONES.items()):
        print(f"{name:22s} ({x:5.1f}, {y:5.1f})")


@handled
def cmd_scaffold(a):
    try:
        spec = scaffold(a.project_id, a.phase, a.focus, a.home, a.away, a.home_base, a.away_base,
                        F.Block.parse(a.home_block) if a.home_block else None,
                        F.Block.parse(a.away_block) if a.away_block else None, a.holder)
    except (KeyError, ValueError) as e:
        raise ProjectError(str(e).strip("'\""))
    if a.out:
        out = Path(a.out)
        if out.exists() and not a.force:
            raise ProjectError(f"{out} exists; pass --force to overwrite")
        jsonio.write_json(out, spec)
        print(f"wrote {out} — now fill title, summary, principles, triggers, strengths, weaknesses, counters")
    else:
        print(json.dumps(spec, indent=2))


@handled
def cmd_still(a):
    from tms.state import project as P
    from tms.tactic.still import render_still
    pr = P.load(a.project)
    out = render_still(pr.dir)
    print(f"tactic still: {out}")


def register(sub) -> None:
    p = sub.add_parser("tactic", help="formation templates, zones, tactic_spec scaffolding")
    tsub = p.add_subparsers(dest="tactic_action", required=True)
    t = tsub.add_parser("templates", help="list formation templates (roles by line, left to right)")
    t.set_defaults(func=cmd_templates)
    z = tsub.add_parser("zones", help="list named zones usable as move targets")
    z.set_defaults(func=cmd_zones)
    s = tsub.add_parser("scaffold", help="tactic_spec skeleton with engine-solved positions")
    s.add_argument("--project-id", required=True)
    s.add_argument("--phase", required=True)
    s.add_argument("--focus", choices=["H", "A", "both"], default="H")
    s.add_argument("--home", required=True, help="home template, e.g. 3-2-5 (see `tms tactic templates`)")
    s.add_argument("--away", required=True, help="away template, e.g. 4-4-2")
    s.add_argument("--home-base", help="home base formation label, e.g. 4-3-3 (default: template formation)")
    s.add_argument("--away-base")
    s.add_argument("--home-block", help="line_x,depth,width,ball_shift (team-normalized metres)")
    s.add_argument("--away-block")
    s.add_argument("--holder", help="ball holder id (default by phase)")
    s.add_argument("--out", help="write here (e.g. projects/<slug>/artifacts/tactic_spec.json) instead of stdout")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_scaffold)
    st = tsub.add_parser("still", help="render the tactic snapshot to projects/<slug>/renders/tactic_still.png")
    st.add_argument("--project", "-p", metavar="SLUG")
    st.set_defaults(func=cmd_still)
