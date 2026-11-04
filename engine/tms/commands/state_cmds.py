"""Project + stage lifecycle commands: init, use, status, next, stage, approve, reject, key, qa, decision, validate, audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from tms import jsonio, manifest
from tms import validate as V
from tms.commands.common import add_project_arg, emit, handled
from tms.state import approvals, approve_flow, audit as audit_mod, machine, project as P


@handled
def cmd_init(a):
    pr = P.init(a.slug, a.mode, a.title or a.slug, a.dry_run)
    emit({"project": pr.id, "mode": pr.mode, "dir": str(pr.dir), "dry_run": pr.dry_run}, a.json,
         f"created {pr.id} ({pr.mode}{', dry run' if pr.dry_run else ''}) at {pr.dir}\nnext: tms stage begin intake")


@handled
def cmd_use(a):
    P.load(a.slug)
    P.set_active(a.slug)
    print(f"{'this session' if P.current_session() else 'this terminal'} now uses project: {a.slug}")


def _status_text(pr) -> str:
    lines = [f"project {pr.id}  mode={pr.mode}{'  DRY RUN' if pr.dry_run else ''}"]
    for st in machine.all_status(pr):
        opt = " (optional)" if manifest.is_optional(st.stage) else ""
        lines.append(f"  {st.stage:11s} {st.status:15s}{opt}{'  ' + st.reason if st.reason else ''}")
    nxt = machine.next_stage(pr)
    lines.append(f"next: {nxt.stage} ({nxt.status})" if nxt else "next: all required stages completed")
    return "\n".join(lines)


@handled
def cmd_status(a):
    pr = P.load(a.project)
    doc = {"project": pr.id, "mode": pr.mode, "dry_run": pr.dry_run,
           "stages": [s.as_dict() for s in machine.all_status(pr)]}
    nxt = machine.next_stage(pr)
    doc["next"] = nxt.as_dict() if nxt else None
    emit(doc, a.json, _status_text(pr))


@handled
def cmd_next(a):
    pr = P.load(a.project)
    nxt = machine.next_stage(pr)
    if nxt is None:
        emit({"next": None}, a.json, "all required stages completed")
        return
    hint = {
        "not_started": f"tms stage begin {nxt.stage}",
        "in_progress": f"produce {', '.join(manifest.stage_produces(nxt.stage))}; validate; QA; tms stage submit {nxt.stage}",
        "stale": f"{nxt.reason}; fix, re-run QA, then tms stage submit {nxt.stage}",
        "awaiting_human": f"present the work and END YOUR TURN; {nxt.reason}",
    }[nxt.status]
    emit({**nxt.as_dict(), "do": hint, "skill": manifest.stage(nxt.stage)["skill"]}, a.json,
         f"{nxt.stage}: {nxt.status}\n  do: {hint}\n  skill: {manifest.stage(nxt.stage)['skill']}")


@handled
def cmd_stage(a):
    pr = P.load(a.project)
    if a.action == "begin":
        res = machine.begin(pr, a.stage)
    else:
        res = machine.submit(pr, a.stage)
    emit(res, a.json, json.dumps(res, indent=2))


@handled
def cmd_approve(a):
    pr = approve_flow.tty_project(a.word, a.project)
    rec = approve_flow.approve_tty(pr, a.word)
    print(f"approved: {rec['id']} project={pr.id} stage={rec['stage']} key_id={rec['key_id']}")


@handled
def cmd_reject(a):
    pr = approve_flow.tty_project(a.word, a.project)
    stage = approve_flow.reject_tty(pr, a.word, a.reason)
    print(f"rejected: project={pr.id} stage={stage}")


@handled
def cmd_key(a):
    if a.key_action == "migrate":
        res = approve_flow.migrate_keys_tty()
        print(f"migrated: signing key {res['signing_key_id']} in {res['key_dir']}; "
              f"newly trusted: {', '.join(res['imported']) or 'none'}")
        print("every process now uses this location. Check a project with: tms audit -p <slug>")
        return
    st = approvals.key_status()
    emit(st, a.json, "\n".join([
        f"key dir : {st['key_dir']}", f"signing : {st['signing'] or '(none yet)'}  {st['signing_file'] or ''}",
        f"trusted : {', '.join(st['trusted']) or '(none)'}",
        *[f"old key : {p}" for p in st["old_keys_found"]],
        "migration pending: the user runs `tms key migrate` in their own terminal" if st["migration_pending"]
        else "migration: not needed"]))


@handled
def cmd_qa(a):
    pr = P.load(a.project)
    try:
        review = jsonio.read_json(Path(a.review))
    except FileNotFoundError:
        raise P.ProjectError(f"review file not found: {a.review}")
    except ValueError as e:
        raise P.ProjectError(f"review file is not valid UTF-8 JSON: {e}")
    rec = machine.record_qa(pr, a.stage, a.agent, review)
    emit(rec, a.json, f"recorded {rec['id']}: {a.agent} round {rec['round']} verdict={rec['verdict']}")


def _sync_test(a):
    from tms.qa.sync import cmd_sync_test
    return cmd_sync_test(a)


@handled
def cmd_decision(a):
    pr = P.load(a.project)
    rec = machine.log_decision(pr, a.category, a.by, a.text, a.stage)
    print(f"{rec['id']}: {rec['text']}")


@handled
def cmd_validate(a):
    if a.hook:  # PostToolUse: validate the single file just written; silent unless it is an artifact
        hit = manifest.artifact_for_path(Path(a.hook))
        if hit is None:
            return 0
        pdir, name = hit
        findings = V.validate_file(pdir, name)
        errs = V.errors_only(findings)
        if errs:
            msg = "\n".join(f"[{f.rule}] {f.location + ': ' if f.location else ''}{f.message}" for f in errs[:20])
            print(f"{name}.json failed validation — fix these before continuing:\n{msg}", file=sys.stderr)
            return 2
        return 0
    pr = P.load(a.project)
    if a.file:  # validate a draft (e.g. projects/<slug>/drafts/x.json) as artifact NAME in this project's context
        if len(a.names) != 1:
            raise P.ProjectError("--file needs exactly one artifact name, e.g. `tms validate tactic_spec --file draft.json`")
        try:
            doc = jsonio.read_json(Path(a.file))
        except (FileNotFoundError, ValueError) as e:
            raise P.ProjectError(f"cannot read {a.file}: {e}")
        fs = V.validate_doc(a.names[0], doc, V.Context(project_dir=pr.dir, mode=pr.mode))
        for f in fs:
            print(f"  {f.severity.upper():7s} [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}")
        n_err = len(V.errors_only(fs))
        print(f"{a.names[0]} draft: {n_err} error(s), {len(fs) - n_err} warning(s)")
        return 1 if n_err else 0
    names = a.names or [n for n in manifest.artifact_names() if pr.artifact_path(n).is_file()]
    report, n_err = {}, 0
    for n in names:
        fs = V.validate_file(pr.dir, n, pr.mode)
        report[n] = [f.as_dict() for f in fs]
        n_err += len(V.errors_only(fs))
    if a.json:
        print(json.dumps({"errors": n_err, "findings": report}, indent=2))
    else:
        for n, fs in report.items():
            print(f"{n}: {'OK' if not fs else ''}")
            for f in fs:
                print(f"  {f['severity'].upper():7s} [{f['rule']}] {f['location'] + ': ' if f['location'] else ''}{f['message']}")
        print(f"{n_err} error(s)")
    return 1 if n_err else 0


@handled
def cmd_audit(a):
    pr = P.load(a.project)
    problems = audit_mod.audit(pr)
    emit({"project": pr.id, "problems": problems}, a.json,
         "\n".join([f"audit {pr.id}: {'OK' if not problems else str(len(problems)) + ' problem(s)'}"] + [f"  - {p}" for p in problems]))
    return 1 if problems else 0


def register(sub) -> None:
    p = sub.add_parser("init", help="create a project")
    p.add_argument("slug")
    p.add_argument("--mode", required=True, choices=manifest.modes())
    p.add_argument("--title")
    p.add_argument("--dry-run", action="store_true", help="mock providers only; zero cost")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("use", help="set the active project")
    p.add_argument("slug")
    p.set_defaults(func=cmd_use)

    for name, fn, hlp in (("status", cmd_status, "derived status of every stage"),
                          ("next", cmd_next, "the next thing to do (trust this over memory)")):
        p = sub.add_parser(name, help=hlp)
        add_project_arg(p)
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=fn)

    p = sub.add_parser("stage", help="begin or submit a stage")
    p.add_argument("action", choices=["begin", "submit"])
    p.add_argument("stage")
    add_project_arg(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("approve", help="USER ONLY: approve a stage from your own interactive terminal")
    p.add_argument("word", help="tactic | analysis | storyboard | final | package")
    add_project_arg(p)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("reject", help="USER ONLY: reject a stage from your own interactive terminal")
    p.add_argument("word", help="tactic | analysis | storyboard | final | package")
    p.add_argument("--reason", required=True, help="what to change")
    add_project_arg(p)
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("key", help="approval keys: status (read-only, ids only) or migrate (USER ONLY)")
    p.add_argument("key_action", choices=["status", "migrate"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_key)

    p = sub.add_parser("qa", help="record a reviewer subagent's qa_review (binds it to current artifact hashes)")
    qsub = p.add_subparsers(dest="qa_action", required=True)
    r = qsub.add_parser("record")
    r.add_argument("stage")
    r.add_argument("--agent", required=True)
    r.add_argument("--review", required=True, help="path to the qa_review JSON returned by the reviewer")
    add_project_arg(r)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_qa)
    st = qsub.add_parser("sync-test", help="end-to-end A/V sync calibration: rendered flashes vs muxed audio clicks")
    st.add_argument("--keep", metavar="DIR", help="keep the calibration files in DIR")
    st.set_defaults(func=_sync_test)

    p = sub.add_parser("decision", help="append to the decision log")
    dsub = p.add_subparsers(dest="decision_action", required=True)
    d = dsub.add_parser("add")
    d.add_argument("--category", required=True,
                   choices=["creative", "tactical", "data", "budget", "provider", "fallback", "scope", "process"])
    d.add_argument("--by", required=True, choices=["user", "agent"])
    d.add_argument("--text", required=True)
    d.add_argument("--stage")
    add_project_arg(d)
    d.set_defaults(func=cmd_decision)

    p = sub.add_parser("validate", help="schema + rule validation of artifacts")
    p.add_argument("names", nargs="*", help="artifact names (default: all present)")
    p.add_argument("--hook", metavar="PATH", help="validate one written file (used by the PostToolUse hook)")
    p.add_argument("--file", metavar="PATH", help="validate a draft file as the single named artifact")
    add_project_arg(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("audit", help="verify approvals, QA bindings, snapshots, decision log")
    add_project_arg(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit)
