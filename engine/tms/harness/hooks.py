"""Hook event handlers shared by Claude Code and Codex.

Both harnesses send JSON on stdin with `hook_event_name`, `tool_name`, `tool_input`, `cwd`, `session_id`.
Differences we normalise:
  * file edits — Claude: Write/Edit/MultiEdit/NotebookEdit with tool_input.file_path (or notebook_path);
                 Codex:  apply_patch with the patch text in tool_input.command (paths in *** headers).
  * shell      — Bash / PowerShell; Codex may send command as a string or an argv list.
Outputs use the formats both harnesses accept:
  * PreToolUse deny  -> stdout JSON hookSpecificOutput.permissionDecision="deny" (exit 0)
  * PostToolUse block -> exit 2 with the reason on stderr
  * Stop block        -> stdout JSON {"decision":"block","reason":...}; exit 0 with {} otherwise
  * context injection -> stdout JSON hookSpecificOutput.additionalContext
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from tms import paths
from tms.harness import policy

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
# mcp__terminal__run_in_terminal types into a real terminal (a TTY), so it gets the same command policy as a shell.
SHELL_TOOLS = {"Bash", "PowerShell", "shell", "local_shell", "exec_command", "mcp__terminal__run_in_terminal"}
READ_TOOLS = {"Read"}
# Cheap pre-filter so ordinary prompts skip the imports. Deliberately not anchored: approve_flow decides what counts.
APPROVAL_RE = re.compile(r"\b(approve|reject)\s+[a-z]+\b", re.I)


@dataclass
class Call:
    event: str
    tool: str = ""
    writes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    command: str = ""
    prompt: str = ""
    session_id: str = ""
    stop_hook_active: bool = False
    log_reason: str = ""  # a fixed code for hooks.log, never prompt content


def normalise(payload: dict) -> Call:
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {"command": ti}
    tool = payload.get("tool_name") or ""
    prompt = payload.get("prompt") or ""
    if not isinstance(prompt, str):  # never a whole message: JSON keeps it from matching the approval pattern
        prompt = json.dumps(prompt)
    call = Call(event=payload.get("hook_event_name", ""), tool=tool, prompt=prompt,
                session_id=str(payload.get("session_id") or ""), stop_hook_active=bool(payload.get("stop_hook_active")))
    if tool == "apply_patch":
        call.writes = policy.patch_paths(_as_text(ti.get("command") or ti.get("patch") or ti.get("input")))
    elif tool in EDIT_TOOLS:
        f = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
        call.writes = [f] if f else []
    elif tool in READ_TOOLS:
        f = ti.get("file_path") or ti.get("path")
        call.reads = [f] if f else []
    elif tool in SHELL_TOOLS:
        call.command = _as_text(ti.get("command") or ti.get("cmd"))
    return call


def _as_text(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v or "")


def _ctx(event: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"[tms policy] {reason}"}}


# ------------------------------------------------------------------ handlers
def pre_tool_use(call: Call) -> tuple[int, dict | None, str]:
    for p in call.writes:
        v = policy.check_write(p)
        if v.deny:
            return 0, _deny(v.reason), ""
    for p in call.reads:
        v = policy.check_read(p)
        if v.deny:
            return 0, _deny(v.reason), ""
    if call.command:
        v = policy.check_command(call.command)
        if v.deny:
            return 0, _deny(v.reason), ""
    return 0, None, ""


def _mark_dirty(kind: str) -> None:
    f = paths.scratch_dir() / "dirty.json"
    try:
        kinds = set(json.loads(f.read_text(encoding="utf-8"))) if f.is_file() else set()
    except ValueError:
        kinds = set()
    kinds.add(kind)
    f.write_text(json.dumps(sorted(kinds)), encoding="utf-8")


def post_tool_use(call: Call) -> tuple[int, dict | None, str]:
    problems = []
    for p in call.writes:
        kind = policy.dirty_kind(p)
        if kind:
            _mark_dirty(kind)
        problems += _validate_if_artifact(p)
    if problems:
        return 2, None, "\n".join(problems)
    return 0, None, ""


def _validate_if_artifact(p: str) -> list[str]:
    from tms import manifest
    from tms import validate as V
    path = Path(p)
    if not path.is_absolute():
        path = paths.root() / path
    hit = manifest.artifact_for_path(path)
    if hit is None:
        return []
    pdir, name = hit
    errs = V.errors_only(V.validate_file(pdir, name))
    if not errs:
        return []
    lines = [f"[tms] {name}.json failed validation — fix before continuing:"]
    lines += [f"  [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}" for f in errs[:15]]
    return lines


def _run(argv: list[str], timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, cwd=paths.root(), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 1, f"timed out after {timeout}s: {' '.join(argv)}"


def stop(call: Call) -> tuple[int, dict | None, str]:
    f = paths.scratch_dir() / "dirty.json"
    if not f.is_file():
        return 0, {}, ""
    if call.stop_hook_active:  # never loop: allow the stop, keep the marker for next time
        return 0, {"systemMessage": "[tms] code changed but fast tests still failing; marker kept"}, ""
    kinds = set(json.loads(f.read_text(encoding="utf-8") or "[]"))
    py = str(paths.venv_python())
    failures = []
    code, out = _run([py, "-m", "pytest", "-m", "fast", "-q", "-x", "-p", "no:cacheprovider"], 300)
    if code != 0:
        failures.append("fast tests failed:\n" + "\n".join(out.strip().splitlines()[-25:]))
    if "harness" in kinds or "python" in kinds:
        code, out = _run([py, "-m", "tms", "sync-harness", "--check"], 60)
        if code != 0:
            failures.append("harness mirrors out of date (run `.venv/Scripts/tms sync-harness`):\n" + out[-1500:])
    if "ts" in kinds:
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        code, out = _run([npm, "--prefix", "render", "run", "verify:fast"], 300)
        if code != 0:
            failures.append("render typecheck failed:\n" + "\n".join(out.strip().splitlines()[-25:]))
    if failures:
        return 0, {"decision": "block", "reason": "[tms] verification failed after code changes — fix before finishing:\n\n"
                   + "\n\n".join(failures)}, ""
    f.unlink(missing_ok=True)
    return 0, {}, ""


def user_prompt_submit(call: Call) -> tuple[int, dict | None, str]:
    found = APPROVAL_RE.search(call.prompt or "")
    if not found:
        return 0, None, ""
    try:
        from tms.state import approve_flow
        msg, reason = approve_flow.route_prompt_detail(call.prompt, call.session_id)
        call.log_reason = reason or ""
    except Exception as e:  # noqa: BLE001 — a lost decision must never be silent
        call.log_reason = f"internal_error:{type(e).__name__}"
        msg = (f"[tms] {found.group(1).upper()} NOT RECORDED: the hook failed ({type(e).__name__}). "
               f"The user can run `.venv/Scripts/tms approve <word>` in their own terminal.")
    return 0, (_ctx("UserPromptSubmit", msg) if msg else None), ""


def session_start(call: Call) -> tuple[int, dict | None, str]:
    from tms import envfile
    from tms.state import approvals, machine, project as P
    lines = ["[tms] Tactic Motion Studio. Contract: AGENTS.md. Run tools via .venv/Scripts/tms (never bare python)."]
    if not paths.venv_python().is_file():
        lines.append("[tms] WARNING: .venv missing — run `py -3.12 -m venv .venv` and `pip install -e .[dev]`.")
    keys = [k for k in envfile.SECRET_KEYS if envfile.present(k)]
    lines.append(f"[tms] keys present: {', '.join(keys) or 'none'} (values are never shown)")
    try:
        if approvals.migration_pending():
            lines.append("[tms] approval keys not migrated: approvals made in the chat and in the Terminal panel may not "
                         "verify in each other's view. Only the user can fix this, with `tms key migrate` in the Terminal panel.")
        pr = P.load(P.session_slug(call.session_id))
        st = machine.next_stage(pr)
        lines.append(f"[tms] this session's project: {pr.id} ({pr.mode}{', dry run' if pr.dry_run else ''}); "
                     f"next: {st.stage + ' — ' + st.status + (' (' + st.reason + ')' if st.reason else '') if st else 'all done'}")
    except P.ProjectError as e:
        lines.append(f"[tms] {e}")
    except Exception as e:  # noqa: BLE001 — never fail session start
        lines.append(f"[tms] no project status ({type(e).__name__})")
    return 0, _ctx("SessionStart", "\n".join(lines)), ""


HANDLERS = {
    "pre-tool-use": pre_tool_use,
    "post-tool-use": post_tool_use,
    "stop": stop,
    "user-prompt-submit": user_prompt_submit,
    "session-start": session_start,
}


def main(argv: list[str]) -> int:
    t0 = time.perf_counter()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    if len(argv) != 1 or argv[0] not in HANDLERS:
        print(f"usage: dispatch.py {{{'|'.join(HANDLERS)}}}", file=sys.stderr)
        return 1
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    call = normalise(payload)
    try:
        code, out, err = HANDLERS[argv[0]](call)
    except Exception as e:  # noqa: BLE001 — a crashing hook must not wedge the session; fail open but loudly
        code, out, err = 0, None, f"[tms hook] internal error in {argv[0]}: {type(e).__name__}: {e}"
    if out is not None:
        sys.stdout.write(json.dumps(out))
    if err:
        sys.stderr.write(err + "\n")
    log = paths.scratch_dir() / "hooks.log"
    with open(log, "a", encoding="utf-8") as f:
        entry = {"event": argv[0], "tool": call.tool, "code": code,
                 "decision": (out or {}).get("hookSpecificOutput", {}).get("permissionDecision") or (out or {}).get("decision"),
                 "ms": round((time.perf_counter() - t0) * 1000)}
        if call.log_reason:
            entry["reason"] = call.log_reason
        f.write(json.dumps(entry) + "\n")
    return code
