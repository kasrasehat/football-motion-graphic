"""The only two ways a human approval is created (see approvals.py)."""
from __future__ import annotations

import re
import secrets
import sys

from tms import manifest
from tms.state import approvals, machine
from tms.state.project import GateViolation, Project, ProjectError

# An approval must be the user's WHOLE message: "approve <word>" plus optional trailing punctuation.
# Anything conditional ("approve tactic? not sure", "approve tactic once ...") is NOT an approval.
APPROVE_RE = re.compile(r"^\s*approve\s+([a-z]+)\s*[.!]*\s*$", re.I)
REJECT_RE = re.compile(r"^\s*reject\s+([a-z]+)\b\s*[:\-]?\s*(.*)$", re.I | re.S)
LOOKS_LIKE = re.compile(r"^\s*(approve|reject)\s+[a-z]+\b", re.I)


def _target(project: Project, word: str) -> str:
    stage = manifest.stage_for_word(project.mode, word.lower())
    if stage is None:
        words = [manifest.approval_word(s) for s in project.stages() if manifest.approval_word(s)]
        raise ProjectError(f"unknown approval word {word!r} for mode {project.mode}; use one of {words}")
    return stage


def approve(project: Project, word: str, via: str, session_id: str) -> dict:
    stage = _target(project, word)
    st = machine.status(project, stage)
    if st.status != "awaiting_human":
        raise GateViolation(f"{stage} is {st.status}{' (' + st.reason + ')' if st.reason else ''} — nothing to approve")
    bind = machine.binding_of(st.submit["hashes"], st.submit["input_hashes"])
    return approvals.sign(project, stage, word.lower(), bind, via, session_id)


def handle_prompt(project: Project, prompt: str, session_id: str) -> str | None:
    """Called by the UserPromptSubmit hook with the user's literal message. Returns context text or None."""
    text = prompt or ""
    if not LOOKS_LIKE.match(text):
        return None
    try:
        m = APPROVE_RE.match(text)
        if m:
            rec = approve(project, m.group(1), "prompt-hook", session_id)
            return (f"[tms] APPROVAL RECORDED {rec['id']}: stage '{rec['stage']}' of project {project.id} approved by the "
                    f"user (bound to the submitted artifacts and their inputs). Continue with the next stage.")
        m = REJECT_RE.match(text)
        if m:
            stage = _target(project, m.group(1))
            feedback = m.group(2).strip() or "(no reason given)"
            res = machine.reject(project, stage, feedback)
            machine.log_decision(project, "creative", "user", f"rejected {stage}: {res['feedback']}", stage)
            return (f"[tms] REJECTION RECORDED for stage '{stage}'. The stage is back in progress. "
                    f"User feedback: {res['feedback']} — revise, re-run QA, and resubmit.")
        return ("[tms] APPROVE NOT RECORDED: an approval must be the whole message, exactly `approve <word>`. "
                "Ask the user to confirm explicitly if they meant to approve.")
    except (GateViolation, ProjectError) as e:
        verb = "APPROVE" if text.strip().lower().startswith("approve") else "REJECT"
        return f"[tms] {verb} NOT RECORDED: {e}"


def approve_tty(project: Project, word: str) -> dict:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise GateViolation("`tms approve` must be run by the user in an interactive terminal "
                            "(or the user types `approve <word>` in chat)")
    stage = _target(project, word)
    st = machine.status(project, stage)
    if st.status != "awaiting_human":
        raise GateViolation(f"{stage} is {st.status} — nothing to approve")
    print(f"Project {project.id} — approving stage '{stage}'. Submitted artifacts:")
    for name, h in sorted(st.submit["hashes"].items()):
        print(f"  {name:20s} {h[:16]}…")
    code = secrets.token_hex(2).upper()
    typed = input(f"Type {code} to approve (anything else cancels): ").strip().upper()
    if typed != code:
        raise GateViolation("approval cancelled")
    bind = machine.binding_of(st.submit["hashes"], st.submit["input_hashes"])
    return approvals.sign(project, stage, word.lower(), bind, "tty", "terminal")
