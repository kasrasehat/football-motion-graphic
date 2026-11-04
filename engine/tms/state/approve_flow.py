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
# Claude Code joins a turn's content blocks with newlines into the hook's `prompt`, so a reminder delivered with a user
# message arrives as "<system-reminder>...</system-reminder>\n\n\napprove analysis". The payload marks no boundary between
# added text and the user's words, and pasted or relayed text can imitate the markup. So this text is never stripped to
# find an approval; it only explains a refusal. See tests/harness/test_approval_injection.py.
HARNESS_TEXT = re.compile(r"</?(system-reminder|pasted_content|side-sessions-event|ci-monitor-event)\b", re.I)
TERMINAL_HINT = "The user can resend it alone, or run `.venv/Scripts/tms approve <word>` in their own terminal."


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


def embedded_decision(text: str) -> str | None:
    """The verb of an approval-like phrase anywhere in the text. For reporting only: it can never record anything."""
    words = {w for mode in ("tactic", "match_preview") for w in map(manifest.approval_word, manifest.mode_stages(mode)) if w}
    m = re.search(rf"\b(approve|reject)\s+(?:{'|'.join(sorted(words))})\b", text or "", re.I)
    return m.group(1).upper() if m else None


def _refusal(verb: str, text: str) -> tuple[str, str]:
    if HARNESS_TEXT.search(text):
        return (f"[tms] {verb} NOT RECORDED: the message reached the hook with other text attached (such as a reminder or "
                f"pasted content), and the hook cannot tell that text from the user's words, so it does not count. "
                f"Do not treat the stage as decided. If the user did not mean to decide it, ignore this. {TERMINAL_HINT}",
                "harness_text_attached")
    return (f"[tms] {verb} NOT RECORDED: a decision must be the user's whole message, exactly `{verb.lower()} <word>`; "
            f"anything conditional or surrounded by other text does not count. Do not treat the stage as decided. "
            f"If the user did not mean to decide it, ignore this. {TERMINAL_HINT}", "not_whole_message")


def handle_prompt_detail(project: Project, prompt: str, session_id: str) -> tuple[str | None, str | None]:
    """(context text, reason code). The code is a fixed string, safe to log; a refusal never echoes the prompt."""
    text = prompt or ""
    if not LOOKS_LIKE.match(text):
        verb = embedded_decision(text)
        return _refusal(verb, text) if verb else (None, None)
    verb = "APPROVE" if text.strip().lower().startswith("approve") else "REJECT"
    try:
        m = APPROVE_RE.match(text)
        if m:
            rec = approve(project, m.group(1), "prompt-hook", session_id)
            return (f"[tms] APPROVAL RECORDED {rec['id']}: stage '{rec['stage']}' of project {project.id} approved by the "
                    f"user (bound to the submitted artifacts and their inputs). Continue with the next stage."), None
        m = REJECT_RE.match(text) if not HARNESS_TEXT.search(text) else None
        if m:
            stage = _target(project, m.group(1))
            feedback = m.group(2).strip() or "(no reason given)"
            res = machine.reject(project, stage, feedback)
            machine.log_decision(project, "creative", "user", f"rejected {stage}: {res['feedback']}", stage)
            return (f"[tms] REJECTION RECORDED for stage '{stage}'. The stage is back in progress. "
                    f"User feedback: {res['feedback']} — revise, re-run QA, and resubmit."), None
        return _refusal(verb, text)
    except (GateViolation, ProjectError) as e:
        return f"[tms] {verb} NOT RECORDED: {e}", "gate_refused"


def handle_prompt(project: Project, prompt: str, session_id: str) -> str | None:
    """Called with the prompt the hook received. Returns context text or None."""
    return handle_prompt_detail(project, prompt, session_id)[0]


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
