"""Stage lifecycle with derived status.

    not_started -> (begin) -> in_progress -> (submit: validators + QA bound to hashes) ->
        gate=none  -> completed
        gate=human -> awaiting_human -> (signed approval for the submitted binding) -> completed
    any change to a produced OR input artifact after submit -> stale (approval and reviews void; resubmit needed)

The *binding* of a stage = sha256 of every produced artifact plus every input artifact ("in:<name>").
Approvals and QA reviews are bound to it. Review rounds are counted per *epoch*: an epoch ends at every
submit, reopen or reject of the stage, so a rejected or stale stage always gets fresh rounds.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from tms import jsonio, manifest, schema
from tms import validate as V
from tms.state import approvals
from tms.state.project import GateViolation, Project, ProjectError, next_id


@dataclass
class StageStatus:
    stage: str
    status: str
    reason: str = ""
    submit: dict | None = None
    approval: dict | None = None
    missing_qa: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"stage": self.stage, "status": self.status, "reason": self.reason,
                "approval": self.approval["id"] if self.approval else None}


def _check_stage(project: Project, stage: str) -> None:
    if stage not in project.stages():
        raise ProjectError(f"stage {stage!r} is not part of mode {project.mode}; stages: {', '.join(project.stages())}")


def current_hashes(project: Project, names: list[str]) -> dict[str, str]:
    out = {}
    for n in names:
        p = project.artifact_path(n)
        out[n] = jsonio.sha256_file(p) if p.is_file() else "missing"
    return out


def binding_of(produced: dict[str, str], inputs: dict[str, str]) -> dict[str, str]:
    return dict(sorted({**produced, **{f"in:{k}": v for k, v in inputs.items()}}.items()))


def binding(project: Project, stage: str) -> dict[str, str]:
    return binding_of(current_hashes(project, manifest.stage_produces(stage)),
                      current_hashes(project, manifest.stage_inputs(stage, project.mode)))


def _stage_events(project: Project, stage: str) -> list[dict]:
    return [e for e in project.records("events") if e["stage"] == stage]


def epoch(project: Project, stage: str) -> int:
    return sum(1 for e in _stage_events(project, stage) if e["type"] in ("submit", "reopen", "reject"))


def last_valid_submit(project: Project, stage: str) -> dict | None:
    sub = None
    for e in _stage_events(project, stage):
        if e["type"] == "submit":
            sub = e
        elif e["type"] in ("reopen", "reject"):
            sub = None
    return sub


def upstream(project: Project, stage: str) -> list[str]:
    _check_stage(project, stage)
    stages = project.stages()
    return [s for s in stages[: stages.index(stage)] if not manifest.is_optional(s)]


def status(project: Project, stage: str, _seen: dict | None = None) -> StageStatus:
    cache = _seen if _seen is not None else {}
    if stage in cache:
        return cache[stage]
    _check_stage(project, stage)
    evs = _stage_events(project, stage)
    if not any(e["type"] == "begin" for e in evs):
        st = StageStatus(stage, "not_started")
    else:
        sub = last_valid_submit(project, stage)
        if sub is None:
            st = StageStatus(stage, "in_progress")
        else:
            produced = current_hashes(project, manifest.stage_produces(stage))
            inputs = current_hashes(project, manifest.stage_inputs(stage, project.mode))
            ups = [status(project, u, cache) for u in upstream(project, stage)]
            bad_up = [u.stage for u in ups if u.status != "completed"]
            if produced != sub["hashes"]:
                changed = sorted(k for k in produced if produced[k] != sub["hashes"].get(k))
                st = StageStatus(stage, "stale", f"changed since submit: {', '.join(changed)}", sub)
            elif inputs != sub["input_hashes"]:
                changed = sorted(k for k in inputs if inputs[k] != sub["input_hashes"].get(k))
                st = StageStatus(stage, "stale", f"inputs changed since submit: {', '.join(changed)}", sub)
            elif bad_up:
                st = StageStatus(stage, "stale", f"upstream not completed: {', '.join(bad_up)}", sub)
            elif manifest.gate(stage) == "human":
                appr = approvals.valid_for(project, stage, binding_of(sub["hashes"], sub["input_hashes"]))
                if appr is None:
                    st = StageStatus(stage, "awaiting_human",
                                     f"user must type: approve {manifest.approval_word(stage)}", sub)
                else:
                    st = StageStatus(stage, "completed", f"approved {appr['id']} via {appr['via']}", sub, appr)
            else:
                st = StageStatus(stage, "completed", "", sub)
    cache[stage] = st
    return st


def all_status(project: Project) -> list[StageStatus]:
    cache: dict = {}
    return [status(project, s, cache) for s in project.stages()]


def next_stage(project: Project) -> StageStatus | None:
    for st in all_status(project):
        if st.status == "completed":
            continue
        if manifest.is_optional(st.stage) and st.status == "not_started":
            continue
        return st
    return None


# ---------------------------------------------------------------- transitions
def _append(project: Project, kind: str, defname: str, rec: dict) -> dict:
    rec = approvals.seal(rec)
    errs = schema.errors(schema.state_validator(defname), rec)
    if errs:
        raise ProjectError(f"internal: bad {defname} record: " + "; ".join(errs))
    jsonio.append_jsonl(project.record_file(kind), rec)
    return rec


def _event(project: Project, **kw) -> dict:
    return _append(project, "events", "event", {"ts": jsonio.now_iso(), **kw})


def require_upstream_completed(project: Project, stage: str) -> None:
    cache: dict = {}
    bad = [(u, status(project, u, cache)) for u in upstream(project, stage)]
    bad = [(u, s) for u, s in bad if s.status != "completed"]
    if bad:
        detail = "; ".join(f"{u}={s.status}{' (' + s.reason + ')' if s.reason else ''}" for u, s in bad)
        raise GateViolation(f"cannot work on {stage}: upstream not completed: {detail}")


def begin(project: Project, stage: str) -> dict:
    require_upstream_completed(project, stage)
    st = status(project, stage)
    if st.status == "in_progress":
        return {"stage": stage, "status": "in_progress", "note": "already in progress"}
    kind = "begin" if st.status == "not_started" else "reopen"
    if kind == "reopen":
        _event(project, type="reopen", stage=stage, note=f"reopened from {st.status}")
    _event(project, type="begin", stage=stage)
    return {"stage": stage, "status": "in_progress", "note": kind}


def require_active(project: Project, stage: str) -> None:
    """Engine commands that build a stage's artifacts call this first."""
    require_upstream_completed(project, stage)
    st = status(project, stage)
    if st.status not in ("in_progress", "stale"):
        raise GateViolation(f"stage {stage} is {st.status}; run `tms stage begin {stage}` first")


def _epoch_records(project: Project, stage: str) -> list[dict]:
    ep = epoch(project, stage)
    return [r for r in project.records("qa") if r["stage"] == stage and r.get("epoch") == ep]


def qa_gaps(project: Project, stage: str, bind: dict[str, str]) -> list[str]:
    """QR-01: in the current epoch each required reviewer has >= min_rounds records, the last passing on `bind`."""
    gaps = []
    recs = _epoch_records(project, stage)
    for q in manifest.stage_qa(stage, project.mode):
        mine = [r for r in recs if r["agent"] == q["agent"]]
        if len(mine) < q["min_rounds"]:
            gaps.append(f"{q['agent']}: {len(mine)}/{q['min_rounds']} review rounds recorded for this submission")
        elif mine[-1]["verdict"] != "pass":
            gaps.append(f"{q['agent']}: last verdict is {mine[-1]['verdict']}")
        elif mine[-1]["reviewed"] != bind:
            gaps.append(f"{q['agent']}: last review was on different artifact/input versions (re-review needed)")
    return gaps


def submit(project: Project, stage: str) -> dict:
    require_upstream_completed(project, stage)
    st = status(project, stage)
    if st.status == "not_started":
        raise GateViolation(f"stage {stage} not begun")
    if st.status in ("awaiting_human", "completed"):
        return {"stage": stage, "status": st.status, "note": "already submitted; nothing changed"}
    problems: list[str] = []
    warnings = 0
    for name in manifest.stage_produces(stage):
        for f in V.validate_file(project.dir, name, project.mode):
            if f.severity == "error":
                problems.append(f"{name}: [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}")
            else:
                warnings += 1
    produced = current_hashes(project, manifest.stage_produces(stage))
    inputs = current_hashes(project, manifest.stage_inputs(stage, project.mode))
    problems += [f"QR-01 {g}" for g in qa_gaps(project, stage, binding_of(produced, inputs))]
    if problems:
        raise GateViolation(f"submit {stage} refused:\n  - " + "\n  - ".join(problems))
    n = sum(1 for e in _stage_events(project, stage) if e["type"] == "submit") + 1
    snap = project.dir / "history" / stage / f"submit-{n:02d}"
    snap.mkdir(parents=True, exist_ok=True)
    for name in manifest.stage_produces(stage):
        shutil.copy2(project.artifact_path(name), snap / f"{name}.json")
    qa_ids = [r["id"] for r in _epoch_records(project, stage)]
    _event(project, type="submit", stage=stage, hashes=produced, input_hashes=inputs,
           snapshot=snap.relative_to(project.dir).as_posix(), warnings=warnings, qa_records=qa_ids)
    after = status(project, stage)
    return {"stage": stage, "status": after.status, "reason": after.reason, "warnings": warnings}


def record_qa(project: Project, stage: str, agent: str, review: dict) -> dict:
    _check_stage(project, stage)
    if not isinstance(review, dict):
        raise ProjectError("review must be a JSON object")
    errs = schema.validate_artifact("qa_review", review)
    if errs:
        raise ProjectError("review does not match qa_review schema:\n  - " + "\n  - ".join(errs))
    if review["stage"] != stage or review["agent"] != agent:
        raise ProjectError(f"review is for {review['stage']}/{review['agent']}, not {stage}/{agent}")
    allowed = [q for q in manifest.stage_qa(stage, project.mode) if q["agent"] == agent]
    if not allowed:
        raise ProjectError(f"{agent} is not a configured reviewer of {stage} in mode {project.mode}")
    st = status(project, stage)
    if st.status not in ("in_progress", "stale"):
        raise GateViolation(f"stage {stage} is {st.status}; reviews are recorded while in progress")
    ep = epoch(project, stage)
    rnd = sum(1 for r in _epoch_records(project, stage) if r["agent"] == agent) + 1
    if rnd > allowed[0]["max_rounds"]:
        raise GateViolation(f"{agent} exceeded max_rounds={allowed[0]['max_rounds']} for {stage}: "
                            "escalate to the user with the open findings")
    records = project.records("qa")
    rid = next_id(records, "Q-")
    rel = f"state/qa/{rid}-{stage}-{agent}.json"
    jsonio.write_json(project.dir / rel, review)
    counts: dict[str, int] = {}
    for f in review["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    rec = {"id": rid, "ts": jsonio.now_iso(), "stage": stage, "agent": agent, "round": rnd, "epoch": ep,
           "verdict": review["verdict"], "reviewed": binding(project, stage), "file": rel,
           "file_sha256": jsonio.sha256_file(project.dir / rel), "counts": counts}
    return _append(project, "qa", "qa_record", rec)


MAX_TEXT = 900


def log_decision(project: Project, category: str, decided_by: str, text: str, stage: str | None) -> dict:
    if stage is not None:
        _check_stage(project, stage)
    text = text.strip()
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1] + "…"
    rec = {"id": next_id(project.records("decisions"), "d-"), "ts": jsonio.now_iso(), "stage": stage,
           "category": category, "decided_by": decided_by, "text": text}
    return _append(project, "decisions", "decision", rec)


def reject(project: Project, stage: str, feedback: str) -> dict:
    _check_stage(project, stage)
    st = status(project, stage)
    if st.status != "awaiting_human":
        raise GateViolation(f"stage {stage} is {st.status}, not awaiting approval")
    note = feedback.strip()[:MAX_TEXT]
    _event(project, type="reject", stage=stage, note=note)
    _event(project, type="begin", stage=stage)
    return {"stage": stage, "status": "in_progress", "feedback": note}
