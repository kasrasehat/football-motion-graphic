"""Two sessions, two projects: approvals, rejections and bare `tms` commands must reach the typing session's project."""
from __future__ import annotations

import pytest

from tms import cli, manifest
from tms.harness import hooks, policy
from tms.state import approve_flow, machine, project as P
from tms.state.project import GateViolation, ProjectError

pytestmark = pytest.mark.fast
A, B = "inverted-full-backs", "aek-athens-real-madrid"


@pytest.fixture
def no_upstream(monkeypatch):
    monkeypatch.setattr(machine, "upstream", lambda project, stage: [])


def in_session(monkeypatch, sid: str | None) -> None:
    if sid:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)
    else:
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


def make(monkeypatch, sid, slug, mode) -> P.Project:
    in_session(monkeypatch, sid)
    return P.init(slug, mode, "t", dry_run=True)


def await_stage(pr: P.Project, stage: str) -> None:
    """Put a stage straight into awaiting_human; these tests are about routing, not about producing artifacts."""
    for name in manifest.stage_produces(stage) + manifest.stage_inputs(stage, pr.mode):
        pr.artifact_path(name).parent.mkdir(parents=True, exist_ok=True)
        pr.artifact_path(name).write_text("{}", encoding="utf-8")
    machine._event(pr, type="begin", stage=stage)
    machine._event(pr, type="submit", stage=stage,
                   hashes=machine.current_hashes(pr, manifest.stage_produces(stage)),
                   input_hashes=machine.current_hashes(pr, manifest.stage_inputs(stage, pr.mode)),
                   snapshot=f"history/{stage}/submit-01", warnings=0, qa_records=[])


def say(sid: str, prompt: str) -> str:
    """What the UserPromptSubmit hook does when the user types `prompt` in session `sid`."""
    _, out, _ = hooks.user_prompt_submit(hooks.Call(event="UserPromptSubmit", prompt=prompt, session_id=sid))
    return out["hookSpecificOutput"]["additionalContext"] if out else ""


@pytest.fixture
def two(monkeypatch, tmp_projects, no_upstream):
    """Session s-a works on a tactic project, then session s-b creates a match preview (the pointer used to move)."""
    a = make(monkeypatch, "s-a", A, "tactic")
    b = make(monkeypatch, "s-b", B, "match_preview")
    in_session(monkeypatch, None)  # the hook process is told its session by the payload, not the environment
    return a, b


# --- the shared word ---------------------------------------------------------------------------------------
def test_shared_word_signs_the_typing_sessions_project_when_both_wait(two):
    a, b = two
    await_stage(a, "storyboard")
    await_stage(b, "storyboard")
    assert "APPROVAL RECORDED" in say("s-a", "approve storyboard")
    assert [r["stage"] for r in a.records("approvals")] == ["storyboard"] and b.records("approvals") == []
    assert a.records("approvals")[0]["session_id"] == "s-a"
    assert "APPROVAL RECORDED" in say("s-b", "approve storyboard")
    assert len(b.records("approvals")) == 1 and len(a.records("approvals")) == 1


def test_shared_word_never_signs_another_sessions_waiting_stage(two):
    a, b = two
    await_stage(b, "storyboard")  # only the OTHER session's stage waits
    msg = say("s-a", "approve storyboard")
    assert "NOT RECORDED" in msg and B in msg and f"--project {B}" in msg
    assert a.records("approvals") == [] and b.records("approvals") == []
    assert machine.status(b, "storyboard").status == "awaiting_human"


def test_reject_goes_to_the_typing_sessions_project(two):
    a, b = two
    await_stage(a, "storyboard")
    await_stage(b, "storyboard")
    assert "REJECTION RECORDED" in say("s-a", "reject storyboard: too busy")  # the pointer last moved to s-b's project
    assert machine.status(a, "storyboard").status == "in_progress"
    assert machine.status(b, "storyboard").status == "awaiting_human"
    assert b.records("decisions") == []


# --- a word that exists only in the other mode ------------------------------------------------------------
def test_word_of_the_other_mode_names_the_project_and_explicit_form_works(two):
    a, b = two
    await_stage(a, "tactic")
    msg = say("s-b", "approve tactic")
    assert "NOT RECORDED" in msg and f"approve tactic --project {A}" in msg
    assert a.records("approvals") == []
    assert "APPROVAL RECORDED" in say("s-b", f"approve tactic --project {A}")
    assert a.records("approvals")[0]["stage"] == "tactic" and b.records("approvals") == []


def test_explicit_reject_keeps_the_reason(two):
    a, _ = two
    await_stage(a, "tactic")
    assert "REJECTION RECORDED" in say("s-b", f"reject tactic -p {A}: wrong full-back height")
    assert "wrong full-back height" in a.records("decisions")[-1]["text"]


@pytest.mark.parametrize("msg", ["approve tactic now", "approve tactic --project nosuch", "approve tactic --project"])
def test_extra_words_never_approve(msg, two):
    a, _ = two
    await_stage(a, "tactic")
    assert "NOT RECORDED" in say("s-a", msg)
    assert a.records("approvals") == []


def test_unbound_session_is_refused_when_two_projects_exist(two):
    a, b = two
    await_stage(a, "storyboard")
    msg = say("s-new", "approve storyboard")
    assert "NOT RECORDED" in msg and f"--project {A}" in msg
    assert a.records("approvals") == [] and b.records("approvals") == []


def test_single_project_needs_no_binding(monkeypatch, tmp_projects, no_upstream):
    a = make(monkeypatch, None, A, "tactic")
    await_stage(a, "tactic")
    assert "APPROVAL RECORDED" in say("any-session", "approve tactic")


# --- bare tms commands -------------------------------------------------------------------------------------
def test_bare_commands_stay_on_the_sessions_project(monkeypatch, two):
    for sid, slug in (("s-a", A), ("s-b", B), ("s-a", A)):
        in_session(monkeypatch, sid)
        assert P.load(None).id == slug


def test_use_in_one_session_does_not_move_another(monkeypatch, two):
    in_session(monkeypatch, "s-a")
    P.set_active(B)
    in_session(monkeypatch, "s-b")
    P.set_active(A)
    assert P.load(None).id == A
    in_session(monkeypatch, "s-a")
    assert P.load(None).id == B


def test_session_init_leaves_the_terminal_pointer_alone(monkeypatch, two):
    in_session(monkeypatch, None)
    with pytest.raises(ProjectError, match="no active project"):
        P.load(None)
    P.set_active(A)  # the user's own terminal
    in_session(monkeypatch, "s-c")
    P.init("third-project", "tactic", "t", dry_run=True)
    in_session(monkeypatch, None)
    assert P.load(None).id == A


def test_unbound_session_gets_a_clean_error_listing_projects(monkeypatch, two, capsys):
    in_session(monkeypatch, "s-new")
    assert cli.main(["status"]) == 1
    err = capsys.readouterr().err
    assert A in err and B in err and "tms use" in err and "Traceback" not in err


def test_terminal_pointer_use_is_announced_when_it_could_be_wrong(monkeypatch, two, capsys):
    in_session(monkeypatch, None)
    P.set_active(B)
    assert P.load(None).id == B
    assert B in capsys.readouterr().err


# --- user-only terminal routes -------------------------------------------------------------------------------
class Tty:
    def __init__(self, monkeypatch, answer=None):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
        # echo back the code the prompt asks for, as a person would
        monkeypatch.setattr("builtins.input", lambda prompt="": answer if answer is not None else prompt.split()[1])


def test_terminal_reject_requires_a_terminal(two):
    a, _ = two
    await_stage(a, "tactic")
    assert cli.main(["reject", "tactic", "-p", A, "--reason", "no"]) == 2
    assert machine.status(a, "tactic").status == "awaiting_human"


def test_terminal_reject_records_the_reason(monkeypatch, two):
    a, _ = two
    await_stage(a, "tactic")
    monkeypatch.setattr(approve_flow, "_require_tty", lambda: None)
    Tty(monkeypatch)
    assert cli.main(["reject", "tactic", "-p", A, "--reason", "wrong height"]) == 0
    assert machine.status(a, "tactic").status == "in_progress"
    assert "wrong height" in a.records("decisions")[-1]["text"]


def test_terminal_without_project_finds_the_only_waiting_one(monkeypatch, two):
    a, b = two
    await_stage(a, "tactic")
    P.set_active(B)  # pointer on a match preview, which has no `tactic` stage
    monkeypatch.setattr(approve_flow, "_require_tty", lambda: None)
    Tty(monkeypatch)
    assert cli.main(["approve", "tactic"]) == 0
    assert a.records("approvals")[0]["via"] == "tty"


def test_terminal_without_project_refuses_when_two_wait(monkeypatch, two, capsys):
    a, b = two
    await_stage(a, "storyboard")
    await_stage(b, "storyboard")
    monkeypatch.setattr(approve_flow, "_require_tty", lambda: None)
    Tty(monkeypatch)
    assert cli.main(["approve", "storyboard"]) == 2
    err = capsys.readouterr().err
    assert A in err and B in err
    assert a.records("approvals") == [] and b.records("approvals") == []


def test_tty_gate_is_real(two):
    a, _ = two
    await_stage(a, "tactic")
    with pytest.raises(GateViolation, match="interactive terminal"):
        approve_flow._require_tty()


@pytest.mark.parametrize("cmd", [".venv/Scripts/tms reject tactic --reason x", ".venv/Scripts/tms.exe key migrate",
                                 "& '.venv\\Scripts\\tms.exe' approve tactic"])
def test_user_only_commands_are_denied_to_agents(cmd):
    assert policy.check_command(cmd).deny


def test_tms_key_status_is_allowed():
    assert not policy.check_command(".venv/Scripts/tms key status").deny


def test_terminal_panel_tool_is_covered_by_the_shell_policy():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "mcp__terminal__run_in_terminal",
               "tool_input": {"command": ".venv\\Scripts\\tms.exe approve tactic"}}
    _, out, _ = hooks.pre_tool_use(hooks.normalise(payload))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# --- the raw traceback ------------------------------------------------------------------------------------
def test_tactic_still_without_a_spec_is_a_clean_error(monkeypatch, two, capsys):
    assert cli.main(["tactic", "still", "-p", B]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR:") and "tactic_spec" in err and B in err


def test_missing_file_anywhere_is_a_clean_error(capsys):
    from tms.commands.common import handled

    @handled
    def boom(_):
        raise FileNotFoundError(2, "No such file", "some/where.json")

    assert boom(None) == 1
    assert "some/where.json" in capsys.readouterr().err
