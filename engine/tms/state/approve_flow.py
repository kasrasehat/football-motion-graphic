"""The only two ways a human approval is created (see approvals.py), and how a message finds its project."""
from __future__ import annotations

import re
import secrets
import sys

from tms import manifest
from tms.state import approvals, machine
from tms.state import project as P
from tms.state.project import GateViolation, Project, ProjectError

# An approval must be the user's WHOLE message: "approve <word>" plus optional trailing punctuation, optionally naming
# the project. Anything conditional ("approve tactic? not sure", "approve tactic once ...") is NOT an approval.
_PROJECT = r"(?:\s+(?:--project|-p)\s+([a-z0-9][a-z0-9-]*))?"
APPROVE_RE = re.compile(rf"^\s*approve\s+([a-z]+){_PROJECT}\s*[.!]*\s*$", re.I)
REJECT_RE = re.compile(rf"^\s*reject\s+([a-z]+)\b{_PROJECT}\s*[:\-]?\s*(.*)$", re.I | re.S)
LOOKS_LIKE = re.compile(r"^\s*(approve|reject)\s+([a-z]+)\b", re.I)
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


def _reject(project: Project, word: str, feedback: str) -> tuple[dict, str]:
    stage = _target(project, word)
    res = machine.reject(project, stage, feedback)
    machine.log_decision(project, "creative", "user", f"rejected {stage}: {res['feedback']}", stage)
    return res, stage


def waiting_for(word: str, exclude: str | None = None) -> list[str]:
    """Slugs of the projects with a stage awaiting this approval word."""
    out = []
    for slug in P.all_slugs():
        if slug == exclude:
            continue
        try:
            pr = P.load(slug)
            stage = manifest.stage_for_word(pr.mode, word.lower())
            if stage and machine.status(pr, stage).status == "awaiting_human":
                out.append(slug)
        except ProjectError:
            continue  # a broken project cannot be a target; `tms audit -p` reports it
    return out


def _hint(verb: str, word: str, exclude: str | None) -> str:
    """Point at other project(s) waiting for this word. Only the user can act on it, by typing the explicit form."""
    others = waiting_for(word, exclude)
    if not others:
        return ""
    forms = " or ".join(f"`{verb} {word.lower()} --project {slug}`" for slug in others)
    return f" Waiting for this word: {', '.join(others)}. If the user meant that, they type {forms}."


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
    """Act on the prompt for a chosen project. (context text, reason code); the code is fixed, safe to log."""
    text = prompt or ""
    looks = LOOKS_LIKE.match(text)
    if not looks:
        verb = embedded_decision(text)
        return _refusal(verb, text) if verb else (None, None)
    verb = looks.group(1).upper()
    try:
        m = APPROVE_RE.match(text)
        if m:
            rec = approve(project, m.group(1), "prompt-hook", session_id)
            return (f"[tms] APPROVAL RECORDED {rec['id']}: stage '{rec['stage']}' of project {project.id} approved by the "
                    f"user (bound to the submitted artifacts and their inputs). Continue with the next stage."), None
        m = REJECT_RE.match(text) if not HARNESS_TEXT.search(text) else None
        if m:
            res, stage = _reject(project, m.group(1), m.group(3).strip() or "(no reason given)")
            return (f"[tms] REJECTION RECORDED for stage '{stage}' of project {project.id}. The stage is back in progress. "
                    f"User feedback: {res['feedback']} — revise, re-run QA, and resubmit."), None
        return _refusal(verb, text)
    except (GateViolation, ProjectError) as e:
        return (f"[tms] {verb} NOT RECORDED for project {project.id}: {e}.{_hint(verb.lower(), looks.group(2), project.id)}",
                "gate_refused")


def handle_prompt(project: Project, prompt: str, session_id: str) -> str | None:
    """Act on the message for an already chosen project. Returns context text or None."""
    return handle_prompt_detail(project, prompt, session_id)[0]


def route_prompt_detail(prompt: str, session_id: str) -> tuple[str | None, str | None]:
    """The UserPromptSubmit hook's entry: the message's explicit project, else the typing session's. Never the pointer."""
    text = prompt or ""
    looks = LOOKS_LIKE.match(text)
    if not looks:  # never a decision, so no project is needed to refuse it
        verb = embedded_decision(text)
        return _refusal(verb, text) if verb else (None, None)
    verb, word = looks.group(1).lower(), looks.group(2)
    m = (APPROVE_RE if verb == "approve" else REJECT_RE).match(text)
    explicit = m.group(2).lower() if m and m.group(2) else None
    try:
        project = P.load(explicit or P.session_slug(session_id))
    except ProjectError as e:
        return f"[tms] {verb.upper()} NOT RECORDED: {e}.{_hint(verb, word, None)}", "project_unavailable"
    return handle_prompt_detail(project, text, session_id)


def route_prompt(prompt: str, session_id: str) -> str | None:
    return route_prompt_detail(prompt, session_id)[0]


def _require_tty() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise GateViolation("this command must be run by the user in an interactive terminal "
                            "(or the user types `approve <word>` / `reject <word>: <reason>` in chat)")


def _confirm(action: str) -> None:
    code = secrets.token_hex(2).upper()
    typed = input(f"Type {code} to {action} (anything else cancels): ").strip().upper()
    if typed != code:
        raise GateViolation(f"{action} cancelled")


def tty_project(word: str, slug: str | None) -> Project:
    """--project, else the only project waiting for this word, else the usual default. Two waiting is never guessed."""
    if slug:
        return P.load(slug)
    waiting = waiting_for(word)
    if len(waiting) > 1:
        raise GateViolation(f"{len(waiting)} projects are waiting for `{word}`: {', '.join(waiting)}. Pass --project <slug>.")
    return P.load(waiting[0] if waiting else None)


def approve_tty(project: Project, word: str) -> dict:
    _require_tty()
    stage = _target(project, word)
    st = machine.status(project, stage)
    if st.status != "awaiting_human":
        raise GateViolation(f"{stage} is {st.status} — nothing to approve")
    print(f"Project {project.id} — approving stage '{stage}'. Submitted artifacts:")
    for name, h in sorted(st.submit["hashes"].items()):
        print(f"  {name:20s} {h[:16]}…")
    _confirm("approve")
    bind = machine.binding_of(st.submit["hashes"], st.submit["input_hashes"])
    return approvals.sign(project, stage, word.lower(), bind, "tty", "terminal")


def reject_tty(project: Project, word: str, reason: str) -> str:
    _require_tty()
    stage = _target(project, word)
    print(f"Project {project.id} — rejecting stage '{stage}': {reason}")
    _confirm("reject")
    _reject(project, word, reason)
    return stage


def migrate_keys_tty() -> dict:
    """User-only: deciding which keys to trust decides which records count."""
    _require_tty()
    print(f"Approval keys will be kept in {approvals.key_dir()}. Old keys found (verify-only from now on):")
    old = approvals.old_key_files()
    for path in old:
        print(f"  {approvals.key_id_of(path)}  {path}")
    if not old:
        print("  (none)")
    _confirm("migrate")
    return approvals.migrate_keys()
