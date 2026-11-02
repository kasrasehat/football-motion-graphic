"""State machine: derived status, gates, staleness, QA binding, approvals (and their forgery), audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tms import cli, jsonio, paths
from tms.state import approve_flow, approvals, audit, machine, project as P
from tms.state.project import GateViolation, ProjectError
from tests.helpers import fixture, place

pytestmark = pytest.mark.fast


def review(stage: str, agent: str, verdict: str = "pass") -> dict:
    r = fixture("qa_review")
    r.update(stage=stage, agent=agent, verdict=verdict)
    if verdict != "pass":
        r["findings"] = [{"severity": "critical", "location": "x", "finding": "broken thing", "proposed_fix": "fix the thing"}]
    return r


@pytest.fixture
def proj(tmp_projects):
    return P.init("fx-ifb-442", "tactic", "test", dry_run=True)


def complete_intake(pr):
    machine.begin(pr, "intake")
    place(pr.dir, "brief", fixture("brief"))
    return machine.submit(pr, "intake")


def submit_tactic(pr):
    machine.begin(pr, "tactic")
    place(pr.dir, "tactic_spec", fixture("tactic_spec"))
    machine.record_qa(pr, "tactic", "tactics-critic", review("tactic", "tactics-critic"))
    return machine.submit(pr, "tactic")


def test_fresh_project_status(proj):
    sts = {s.stage: s.status for s in machine.all_status(proj)}
    assert set(sts.values()) == {"not_started"}
    assert machine.next_stage(proj).stage == "intake"


def test_intake_without_gate_completes_on_submit(proj):
    assert complete_intake(proj)["status"] == "completed"


def test_cannot_begin_before_upstream_completed(proj):
    with pytest.raises(GateViolation):
        machine.begin(proj, "tactic")


def test_submit_refuses_invalid_artifact(proj):
    machine.begin(proj, "intake")
    bad = fixture("brief")
    bad["target_duration_s"] = 500
    place(proj.dir, "brief", bad)
    with pytest.raises(GateViolation, match="SCHEMA|BR-01"):
        machine.submit(proj, "intake")


def test_submit_refuses_without_qa(proj):
    complete_intake(proj)
    machine.begin(proj, "tactic")
    place(proj.dir, "tactic_spec", fixture("tactic_spec"))
    with pytest.raises(GateViolation, match="QR-01"):
        machine.submit(proj, "tactic")


def test_failing_review_blocks_then_passing_review_on_current_hashes_allows(proj):
    complete_intake(proj)
    machine.begin(proj, "tactic")
    place(proj.dir, "tactic_spec", fixture("tactic_spec"))
    machine.record_qa(proj, "tactic", "tactics-critic", review("tactic", "tactics-critic", "fix_and_rereview"))
    with pytest.raises(GateViolation, match="last verdict"):
        machine.submit(proj, "tactic")
    machine.record_qa(proj, "tactic", "tactics-critic", review("tactic", "tactics-critic"))
    spec = fixture("tactic_spec")
    spec["summary"] += " Edited after review."
    place(proj.dir, "tactic_spec", spec)  # edit after the passing review -> review is on old hashes
    with pytest.raises(GateViolation, match="different artifact"):
        machine.submit(proj, "tactic")


def test_max_rounds_escalates(proj):
    complete_intake(proj)
    machine.begin(proj, "tactic")
    place(proj.dir, "tactic_spec", fixture("tactic_spec"))
    for _ in range(3):
        machine.record_qa(proj, "tactic", "tactics-critic", review("tactic", "tactics-critic", "fix_and_rereview"))
    with pytest.raises(GateViolation, match="max_rounds"):
        machine.record_qa(proj, "tactic", "tactics-critic", review("tactic", "tactics-critic"))


def test_gated_stage_awaits_human_then_completes_with_approval(proj):
    complete_intake(proj)
    assert submit_tactic(proj)["status"] == "awaiting_human"
    rec = approve_flow.approve(proj, "tactic", "test", "pytest")
    assert rec["via"] == "test"
    st = machine.status(proj, "tactic")
    assert st.status == "completed" and st.approval["id"] == rec["id"]
    assert audit.audit(proj) == []


def test_editing_approved_artifact_makes_it_stale_and_voids_approval(proj):
    complete_intake(proj)
    submit_tactic(proj)
    approve_flow.approve(proj, "tactic", "test", "pytest")
    spec = fixture("tactic_spec")
    spec["title"] = "Changed title after approval"
    place(proj.dir, "tactic_spec", spec)
    st = machine.status(proj, "tactic")
    assert st.status == "stale" and "tactic_spec" in st.reason
    with pytest.raises(GateViolation):
        machine.begin(proj, "storyboard")


def test_upstream_input_change_makes_downstream_stale(proj):
    complete_intake(proj)
    submit_tactic(proj)
    approve_flow.approve(proj, "tactic", "test", "pytest")
    b = fixture("brief")
    b["audience"] = "expert"
    place(proj.dir, "brief", b)
    assert machine.status(proj, "intake").status == "stale"
    assert machine.status(proj, "tactic").status == "stale"


def test_whitespace_only_reformat_is_not_a_change(proj):
    complete_intake(proj)
    p = proj.artifact_path("brief")
    p.write_text(json.dumps(jsonio.read_json(p), indent=4), encoding="utf-8")
    assert machine.status(proj, "intake").status == "completed"


def test_forged_approval_is_rejected_and_audited(proj):
    complete_intake(proj)
    submit_tactic(proj)
    approve_flow.approve(proj, "tactic", "test", "pytest")
    f = proj.record_file("approvals")
    rec = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
    rec["session_id"] = "forged"  # stage and hashes untouched: only the seal can catch this
    f.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert machine.status(proj, "tactic").status == "awaiting_human"
    assert any("bad signature" in p or "seal invalid" in p for p in audit.audit(proj))


def test_test_channel_refused_on_live_project(tmp_projects):
    pr = P.init("fx-ifb-442", "tactic", "live", dry_run=False)
    complete_intake(pr)
    submit_tactic(pr)
    with pytest.raises(ProjectError, match="dry_run"):
        approve_flow.approve(pr, "tactic", "test", "pytest")


def test_prompt_hook_approval_and_rejection(proj):
    complete_intake(proj)
    submit_tactic(proj)
    msg = approve_flow.handle_prompt(proj, "approve tactic", "sess-1")
    assert "APPROVAL RECORDED" in msg
    assert machine.status(proj, "tactic").status == "completed"
    assert approve_flow.handle_prompt(proj, "approve tactic", "sess-1").startswith("[tms] APPROVE NOT RECORDED")
    assert approve_flow.handle_prompt(proj, "please continue", "sess-1") is None


def test_prompt_rejection_reopens_stage(proj):
    complete_intake(proj)
    submit_tactic(proj)
    msg = approve_flow.handle_prompt(proj, "reject tactic: make the right-back start wider", "s")
    assert "REJECTION RECORDED" in msg
    assert machine.status(proj, "tactic").status == "in_progress"
    assert proj.records("decisions")[-1]["decided_by"] == "user"


def test_approve_word_for_unsubmitted_stage_is_refused(proj):
    complete_intake(proj)
    msg = approve_flow.handle_prompt(proj, "approve storyboard", "s")
    assert "NOT RECORDED" in msg


def test_history_snapshot_written_on_submit(proj):
    complete_intake(proj)
    snap = proj.dir / "history" / "intake" / "submit-01" / "brief.json"
    assert snap.is_file()


def test_no_cli_flag_can_approve():
    parser = cli.build_parser()
    flags = []

    def walk(p):
        for act in p._actions:
            flags.extend(act.option_strings)
            if hasattr(act, "choices") and isinstance(act.choices, dict):
                for sp in act.choices.values():
                    walk(sp)
    walk(parser)
    assert not [f for f in flags if "approv" in f.lower()], flags


def test_cli_approve_requires_a_tty(tmp_projects):
    env = dict(os.environ, TMS_PROJECTS_DIR=str(tmp_projects))
    P.init("fx-ifb-442", "tactic", "t", dry_run=True)
    r = subprocess.run([sys.executable, "-m", "tms", "approve", "tactic", "-p", "fx-ifb-442"], capture_output=True,
                       text=True, env=env, stdin=subprocess.PIPE, cwd=paths.root())
    assert r.returncode == 2 and "interactive terminal" in r.stderr


def test_status_cli_exit_codes(tmp_projects):
    env = dict(os.environ, TMS_PROJECTS_DIR=str(tmp_projects))
    run = lambda *a: subprocess.run([sys.executable, "-m", "tms", *a], capture_output=True, text=True, env=env, cwd=paths.root())
    assert run("init", "cli-proj", "--mode", "tactic", "--dry-run").returncode == 0
    assert run("stage", "begin", "tactic", "-p", "cli-proj").returncode == 2
    assert run("status", "-p", "cli-proj", "--json").returncode == 0
    assert run("status", "-p", "nope").returncode == 1
