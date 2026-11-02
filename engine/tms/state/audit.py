"""`tms audit` — independent consistency check of a project's records (tamper evidence). Never raises on bad data."""
from __future__ import annotations

from tms import jsonio, manifest, schema
from tms.state import approvals, machine
from tms.state.project import Project, ProjectError

KINDS = (("events", "event"), ("approvals", "approval"), ("qa", "qa_record"), ("decisions", "decision"))


def audit(project: Project) -> list[str]:
    problems: list[str] = []
    good: dict[str, list[dict]] = {}
    for kind, defname in KINDS:
        try:
            recs = list(jsonio.read_jsonl(project.record_file(kind)))
        except jsonio.CorruptRecord as e:
            problems.append(f"{kind}: corrupt file ({e})")
            good[kind] = []
            continue
        v = schema.state_validator(defname)
        ok = []
        for i, rec in enumerate(recs):
            errs = schema.errors(v, rec, limit=3)
            if errs:
                problems += [f"{kind}[{i}]: {e}" for e in errs]
                continue
            if kind == "approvals":  # precise diagnosis (wrong project / key / channel) before the generic seal check
                why = approvals.verify(project, rec)
                if why:
                    problems.append(f"approval {rec['id']}: {why}")
                    continue
            elif not approvals.seal_ok(rec):
                problems.append(f"{kind}[{i}] ({rec.get('id', rec.get('type'))}): seal invalid — record edited, "
                                "not written by tms, or the approval key was replaced")
                continue
            ok.append(rec)
        good[kind] = ok
    for rec in good["qa"]:
        f = project.dir / rec["file"]
        if not f.is_file():
            problems.append(f"qa {rec['id']}: review file missing ({rec['file']})")
        elif jsonio.sha256_file(f) != rec["file_sha256"]:
            problems.append(f"qa {rec['id']}: review file altered after recording")
    for ev in good["events"]:
        if ev["type"] != "submit":
            continue
        snap = project.dir / ev["snapshot"]
        for name, h in ev["hashes"].items():
            f = snap / f"{name}.json"
            if not f.is_file():
                problems.append(f"submit {ev['stage']}@{ev['ts']}: snapshot of {name} missing")
            elif jsonio.sha256_file(f) != h:
                problems.append(f"submit {ev['stage']}@{ev['ts']}: snapshot of {name} altered")
    ids = [r["id"] for r in good["decisions"]]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        problems.append("decision ids not strictly increasing")
    if not any(p.startswith(("events", "approvals")) for p in problems):
        try:
            for st in machine.all_status(project):
                if st.status == "completed" and manifest.gate(st.stage) == "human" and st.approval is None:
                    problems.append(f"{st.stage}: completed without approval (internal error)")
        except ProjectError as e:
            problems.append(str(e))
    return problems
