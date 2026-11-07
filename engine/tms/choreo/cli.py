"""`tms storyboard compile|preview` — compile the scene_plan and render the animatic + contact sheet."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from tms import jsonio, manifest, remotion
from tms import validate as V
from tms.choreo.document import build_doc, load_inputs
from tms.commands.common import add_project_arg, handled
from tms.props.builder import build as build_props
from tms.state import machine, project as P
from tms.timeline import FPS, provisional


def compile_project(pr) -> tuple[dict, list]:
    plan, spec, brief, hashes = load_inputs(pr.dir)
    doc = build_doc(plan, spec, brief, pr.id, hashes)
    jsonio.write_json(pr.artifact_path("choreography"), doc, compact=True)
    findings = V.validate_file(pr.dir, "choreography", pr.mode)
    return doc, findings


def _print_findings(findings) -> int:
    errs = V.errors_only(findings)
    for f in findings:
        print(f"  {f.severity.upper():7s} [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}")
    print(f"choreography: {len(errs)} error(s), {len(findings) - len(errs)} warning(s)")
    return len(errs)


def compile_draft(pr, plan_path: Path) -> tuple[dict, list]:
    """Compile a draft scene_plan in memory (nothing written) and validate it in the project's context."""
    try:
        plan = jsonio.read_json(plan_path)
    except (FileNotFoundError, ValueError) as e:
        raise P.ProjectError(f"cannot read draft {plan_path}: {e}")
    errs = V.validate_doc("scene_plan", plan, V.Context(project_dir=pr.dir, mode=pr.mode))
    if V.errors_only(errs):
        return {}, errs
    _, spec, brief, hashes = load_inputs_no_plan(pr.dir)
    doc = build_doc(plan, spec, brief, pr.id, hashes)
    return doc, V.validate_doc("choreography", doc, V.Context(project_dir=pr.dir, mode=pr.mode, artifacts={"scene_plan": plan}))


def load_inputs_no_plan(project_dir):
    spec = jsonio.read_json(manifest.artifact_path(project_dir, "tactic_spec"))
    brief = jsonio.read_json(manifest.artifact_path(project_dir, "brief"))
    return None, spec, brief, {}


@handled
def cmd_compile(a):
    pr = P.load(a.project)
    if a.plan:
        doc, findings = compile_draft(pr, Path(a.plan))
        if doc:
            print(f"draft compiled: {len(doc['scenes'])} scenes, {doc['tracks']['n'] / FPS:.1f} s authored (nothing written)")
        return 1 if _print_findings(findings) else 0
    machine.require_active(pr, "storyboard")
    doc, findings = compile_project(pr)
    print(f"compiled {len(doc['scenes'])} scenes, {doc['tracks']['n'] / FPS:.1f} s authored -> build/choreography.json")
    return 1 if _print_findings(findings) else 0


def contact_sheet(video: Path, frames: list[int], out: Path, cols: int = 4) -> None:
    with tempfile.TemporaryDirectory(prefix="tms sheet ") as td:
        tdp = Path(td)
        for k, f in enumerate(frames):
            subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-ss", f"{f / FPS:.3f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=640:-2", str(tdp / f"p{k:03d}.png")], check=True)
        rows = (len(frames) + cols - 1) // cols
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(tdp / "p%03d.png"),
                        "-vf", f"tile={cols}x{rows}:padding=6:margin=6:color=0x111111", "-frames:v", "1", str(out)], check=True)


def preview(pr, scale: float = 0.5, render: bool = True) -> dict:
    doc, findings = compile_project(pr)
    narration = pr.load_artifact("narration_script")
    plan = pr.load_artifact("scene_plan")
    spec = pr.load_artifact("tactic_spec")
    brief = pr.load_artifact("brief")
    if narration is None:
        raise P.ProjectError("narration_script.json is missing — the storyboard needs scene_plan AND narration_script")
    tl = provisional(doc, narration, pr.id)
    props = build_props(doc, tl, brief, narration, plan, spec, scale=scale,
                        dossier=pr.load_artifact("match_dossier"), prediction=pr.load_artifact("prediction"),
                        analysis=pr.load_artifact("match_analysis"), project_dir=pr.dir)
    from tms.render.stage import caption_place  # same placement as the final render, or reviewers can't see it
    for c in props["captions"]:
        c["place"] = caption_place(props, c)
    pdir = pr.dir / "renders" / "preview"
    jsonio.write_json(pdir / "props.json", props, compact=True)
    jsonio.write_json(pdir / "timeline.json", tl)
    out = {"findings": findings, "frames": tl["frames"], "props": pdir / "props.json"}
    if render:
        video = pr.dir / "renders" / "animatic.mp4"
        remotion.render("TacticVideo", video, props=pdir / "props.json", timeout=3600)
        marks = sorted({(s["from"] + s["to"]) // 2 for s in tl["scenes"]})
        sheet = pr.dir / "renders" / "contact_sheet.png"
        contact_sheet(video, marks, sheet)
        jsonio.write_json(pr.dir / "renders" / "contact_sheet.json",
                          {"panels": [{"panel": k + 1, "frame": f, "scene": next(s["id"] for s in tl["scenes"] if s["from"] <= f < s["to"])}
                                      for k, f in enumerate(marks)]})
        out.update(video=video, sheet=sheet)
    return out


@handled
def cmd_preview(a):
    pr = P.load(a.project)
    machine.require_active(pr, "storyboard")
    res = preview(pr, scale=a.scale, render=not a.no_render)
    n_err = _print_findings(res["findings"])
    print(f"timeline (provisional, silent): {res['frames']} frames = {res['frames'] / FPS:.1f} s")
    if "video" in res:
        print(f"animatic: {res['video']}\ncontact sheet: {res['sheet']} (panels listed in contact_sheet.json)")
    return 1 if n_err else 0


def register(sub) -> None:
    p = sub.add_parser("storyboard", help="compile the scene_plan; render the animatic preview")
    ssub = p.add_subparsers(dest="storyboard_action", required=True)
    c = ssub.add_parser("compile", help="scene_plan + tactic_spec -> build/choreography.json, then CH validation")
    add_project_arg(c)
    c.add_argument("--plan", metavar="PATH", help="compile a DRAFT scene_plan in memory and report findings (writes nothing)")
    c.set_defaults(func=cmd_compile)
    v = ssub.add_parser("preview", help="compile + silent animatic (renders/animatic.mp4) + contact sheet")
    add_project_arg(v)
    v.add_argument("--scale", type=float, default=0.5, help="render scale (0.5 = 960x540 for 16:9)")
    v.add_argument("--no-render", action="store_true", help="build props only")
    v.set_defaults(func=cmd_preview)
