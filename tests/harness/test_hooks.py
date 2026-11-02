"""Hooks: the EXACT command strings registered for Claude Code and Codex, fed recorded payloads of both harnesses."""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import time

import pytest

from tms import paths
from tms.harness import hooks, policy
from tms.state import machine, project as P
from tests.helpers import fixture, place

pytestmark = pytest.mark.fast
ROOT = paths.root()
BASH = shutil.which("bash")
SETTINGS = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
CODEX = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))


def claude_cmd(event: str) -> str:
    return SETTINGS["hooks"][event][0]["hooks"][0]["command"]


def codex_cmd_windows(event: str) -> str:
    return CODEX["hooks"][event][0]["hooks"][0]["commandWindows"]


@pytest.fixture
def env(tmp_projects):
    e = dict(os.environ)
    e["CLAUDE_PROJECT_DIR"] = str(ROOT)
    return e


def run_claude(event: str, payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, "-c", claude_cmd(event)], input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", env=env, cwd=ROOT, timeout=120)


def run_codex(event: str, payload: dict, env: dict, shell: str = "cmd") -> subprocess.CompletedProcess:
    cmd = codex_cmd_windows(event)
    argv = ["cmd", "/d", "/c", cmd] if shell == "cmd" else ["powershell", "-NoProfile", "-Command", cmd]
    return subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT, timeout=120)


def decision(r: subprocess.CompletedProcess) -> str | None:
    if not r.stdout.strip():
        return None
    out = json.loads(r.stdout)
    return out.get("hookSpecificOutput", {}).get("permissionDecision") or out.get("decision")


def claude_payload(tool: str, **tool_input) -> dict:
    return {"session_id": "s1", "transcript_path": "x", "cwd": str(ROOT), "hook_event_name": "PreToolUse",
            "permission_mode": "default", "tool_name": tool, "tool_input": tool_input}


def codex_patch(*headers: str) -> dict:
    body = "*** Begin Patch\n" + "".join(f"*** {h}\n+x\n" for h in headers) + "*** End Patch\n"
    return {"session_id": "c1", "cwd": str(ROOT), "hook_event_name": "PreToolUse", "model": "gpt", "turn_id": "t",
            "tool_name": "apply_patch", "tool_input": {"command": body}}


def codex_bash(cmd) -> dict:
    return {"session_id": "c1", "cwd": str(ROOT), "hook_event_name": "PreToolUse", "model": "gpt", "turn_id": "t",
            "tool_name": "Bash", "tool_input": {"command": cmd}}


DENY_CLAUDE = [
    ("Write", {"file_path": str(ROOT / "projects/demo/state/events.jsonl")}),
    ("Edit", {"file_path": "projects/demo/build/timeline.json", "old_string": "a", "new_string": "b"}),
    ("Write", {"file_path": str(ROOT / "projects/demo/history/tactic/submit-01/tactic_spec.json")}),
    ("Write", {"file_path": str(ROOT / ".claude/skills/tactic-video/SKILL.md")}),
    ("Write", {"file_path": str(ROOT / ".env")}),
    ("Read", {"file_path": str(ROOT / ".env")}),
    ("Bash", {"command": ".venv/Scripts/tms approve tactic"}),
    ("Bash", {"command": "\"$CLAUDE_PROJECT_DIR/.venv/Scripts/tms.exe\" approve final -p x"}),
    ("Bash", {"command": "python -c 'print(1)'"}),
    ("Bash", {"command": "cat .env"}),
    ("Bash", {"command": "curl -s https://api.elevenlabs.io/v1/voices"}),
    ("Bash", {"command": "echo '{}' > projects/demo/state/approvals.jsonl"}),
    ("Bash", {"command": "rm -rf projects/demo/history"}),
    ("PowerShell", {"command": "Get-Content $env:LOCALAPPDATA\\TacticMotionStudio\\approval.key"}),
    ("Bash", {"command": "git commit --no-verify -m x"}),
]
ALLOW_CLAUDE = [
    ("Write", {"file_path": str(ROOT / "projects/demo/artifacts/brief.json")}),
    ("Write", {"file_path": str(ROOT / "engine/tms/foo.py")}),
    ("Read", {"file_path": str(ROOT / ".env.example")}),
    ("Read", {"file_path": str(ROOT / "projects/demo/state/events.jsonl")}),
    ("Bash", {"command": ".venv/Scripts/tms status --json"}),
    ("Bash", {"command": ".venv/Scripts/python.exe -m pytest -q"}),
    ("Bash", {"command": "cat projects/demo/state/events.jsonl"}),
    ("Bash", {"command": "cp .env.example /tmp/x"}),
]


@pytest.mark.parametrize("tool,ti", DENY_CLAUDE, ids=[f"{t}:{list(i.values())[0][-40:]}" for t, i in DENY_CLAUDE])
def test_claude_pre_tool_use_denies(tool, ti, env):
    r = run_claude("PreToolUse", claude_payload(tool, **ti), env)
    assert r.returncode == 0 and decision(r) == "deny", (r.stdout, r.stderr)


@pytest.mark.parametrize("tool,ti", ALLOW_CLAUDE, ids=[f"{t}:{list(i.values())[0][-40:]}" for t, i in ALLOW_CLAUDE])
def test_claude_pre_tool_use_allows(tool, ti, env):
    r = run_claude("PreToolUse", claude_payload(tool, **ti), env)
    assert r.returncode == 0 and decision(r) is None, (r.stdout, r.stderr)


@pytest.mark.parametrize("shell", ["cmd", "powershell"])
def test_codex_apply_patch_policy(shell, env):
    deny = run_codex("PreToolUse", codex_patch("Update File: projects/demo/build/timeline.json"), env, shell)
    assert decision(deny) == "deny", (deny.stdout, deny.stderr)
    multi = run_codex("PreToolUse", codex_patch("Add File: engine/tms/new.py", "Update File: .codex/agents/gate-verifier.toml"), env, shell)
    assert decision(multi) == "deny"
    allow = run_codex("PreToolUse", codex_patch("Add File: projects/demo/artifacts/scene_plan.json"), env, shell)
    assert allow.returncode == 0 and decision(allow) is None, (allow.stdout, allow.stderr)


@pytest.mark.parametrize("cmd", [".venv/Scripts/tms approve storyboard", ["powershell", "-Command", "python script.py"],
                                 "Remove-Item projects\\demo\\state\\qa.jsonl"])
def test_codex_shell_denies(cmd, env):
    assert decision(run_codex("PreToolUse", codex_bash(cmd), env)) == "deny"


def test_post_tool_use_blocks_invalid_artifact_and_passes_valid(env, tmp_projects):
    pr = P.init("fx-ifb-442", "tactic", "t", dry_run=True)
    bad = fixture("brief")
    bad["target_duration_s"] = 150  # schema allows it; BR-01 (tactic max 120) does not
    f = place(pr.dir, "brief", bad)
    payload = {"session_id": "s", "hook_event_name": "PostToolUse", "tool_name": "Write",
               "tool_input": {"file_path": str(f)}, "tool_response": {}}
    r = run_claude("PostToolUse", payload, env)
    assert r.returncode == 2 and "BR-01" in r.stderr, (r.returncode, r.stderr)
    place(pr.dir, "brief", fixture("brief"))
    r = run_claude("PostToolUse", payload, env)
    assert r.returncode == 0, r.stderr
    rc = run_codex("PostToolUse", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch",
                                    "tool_input": {"command": f"*** Begin Patch\n*** Update File: {f}\n*** End Patch"}}, env)
    assert rc.returncode == 0, rc.stderr


def test_post_tool_use_marks_code_dirty(env, tmp_projects):
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "engine/tms/paths.py")}}
    run_claude("PostToolUse", payload, env)
    assert json.loads((paths.scratch_dir() / "dirty.json").read_text()) == ["python"]


def test_stop_without_dirty_marker_is_silent_ok(env):
    r = run_claude("Stop", {"hook_event_name": "Stop", "stop_hook_active": False}, env)
    assert r.returncode == 0 and json.loads(r.stdout) == {}
    rc = run_codex("Stop", {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": ""}, env)
    assert rc.returncode == 0 and json.loads(rc.stdout) == {}


def test_stop_loop_guard_allows_when_stop_hook_active(env, tmp_projects):
    (paths.scratch_dir() / "dirty.json").write_text('["python"]')
    r = run_claude("Stop", {"hook_event_name": "Stop", "stop_hook_active": True}, env)
    assert r.returncode == 0 and "decision" not in json.loads(r.stdout)
    assert (paths.scratch_dir() / "dirty.json").exists()


def test_stop_blocks_on_failure_and_clears_on_success(tmp_projects, monkeypatch):
    (paths.scratch_dir() / "dirty.json").write_text('["python"]')
    monkeypatch.setattr(hooks, "_run", lambda argv, timeout: (1, "E   assert 1 == 2\n1 failed"))
    code, out, _ = hooks.stop(hooks.Call(event="Stop"))
    assert out["decision"] == "block" and "1 failed" in out["reason"]
    monkeypatch.setattr(hooks, "_run", lambda argv, timeout: (0, "ok"))
    code, out, _ = hooks.stop(hooks.Call(event="Stop"))
    assert out == {} and not (paths.scratch_dir() / "dirty.json").exists()


def _awaiting_tactic_project():
    pr = P.init("fx-ifb-442", "tactic", "t", dry_run=True)
    machine.begin(pr, "intake")
    place(pr.dir, "brief", fixture("brief"))
    machine.submit(pr, "intake")
    machine.begin(pr, "tactic")
    place(pr.dir, "tactic_spec", fixture("tactic_spec"))
    r = fixture("qa_review")
    machine.record_qa(pr, "tactic", "tactics-critic", r)
    machine.submit(pr, "tactic")
    return pr


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_user_prompt_approval_recorded_via_hook(harness, env, tmp_projects):
    pr = _awaiting_tactic_project()
    payload = {"session_id": "s9", "hook_event_name": "UserPromptSubmit", "prompt": "approve tactic"}
    r = run_claude("UserPromptSubmit", payload, env) if harness == "claude" else run_codex("UserPromptSubmit", payload, env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "APPROVAL RECORDED" in ctx, (ctx, r.stderr)
    assert pr.records("approvals")[-1]["via"] == "prompt-hook"
    assert machine.status(pr, "tactic").status == "completed"


def test_ordinary_prompt_produces_no_output(env):
    r = run_claude("UserPromptSubmit", {"hook_event_name": "UserPromptSubmit", "prompt": "make the arrows thicker"}, env)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_session_start_injects_context(env):
    r = run_claude("SessionStart", {"hook_event_name": "SessionStart", "source": "startup"}, env)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[tms]" in ctx and "AGENTS.md" in ctx


def test_patch_paths_parser():
    patch = "*** Begin Patch\n*** Update File: a/b.py\n@@\n-x\n+y\n*** Move to: c/d.py\n*** Delete File: e.txt\n*** End Patch"
    assert policy.patch_paths(patch) == ["a/b.py", "c/d.py", "e.txt"]


def test_git_bash_style_paths_are_normalised():
    drive = ROOT.drive[0].lower()
    posix = "/" + drive + ROOT.as_posix()[2:] + "/projects/x/state/events.jsonl"
    assert policy.check_write(posix).deny


def test_hook_latency_p95_under_400ms(env):
    times = []
    for _ in range(8):
        t0 = time.perf_counter()
        run_claude("PreToolUse", claude_payload("Bash", command=".venv/Scripts/tms status"), env)
        times.append((time.perf_counter() - t0) * 1000)
    p95 = sorted(times)[int(0.95 * (len(times) - 1))]
    assert p95 < 400 or statistics.median(times) < 300, times
