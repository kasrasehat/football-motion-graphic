"""Regression tests for the M1 gate review findings. Each test fails if its defect returns."""
from __future__ import annotations

import json
import os

import pytest

from tms import paths
from tms.state import approve_flow, approvals, audit, machine, project as P
from tms.state.project import GateViolation, ProjectError
from tests.helpers import fixture, place

pytestmark = pytest.mark.fast


def review(stage, agent, verdict="pass"):
    r = fixture("qa_review")
    r.update(stage=stage, agent=agent, verdict=verdict)
    if verdict != "pass":
        r["findings"] = [{"severity": "critical", "location": "x", "finding": "broken thing", "proposed_fix": "fix it"}]
    return r


def make(tmp, slug="fx-ifb-442", dry=True):
    return P.init(slug, "tactic", "t", dry_run=dry)


def intake(pr, brief=None):
    machine.begin(pr, "intake")
    place(pr.dir, "brief", brief or fixture("brief"))
    machine.submit(pr, "intake")


def tactic_awaiting(pr):
    machine.begin(pr, "tactic")
    place(pr.dir, "tactic_spec", fixture("tactic_spec"))
    machine.record_qa(pr, "tactic", "tactics-critic", review("tactic", "tactics-critic"))
    return machine.submit(pr, "tactic")


# --- finding 1: inputs bind approvals and reviews -------------------------------------------
def test_input_change_voids_approval_and_reviews(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    tactic_awaiting(pr)
    approve_flow.approve(pr, "tactic", "test", "t")
    assert machine.status(pr, "tactic").status == "completed"
    b = fixture("brief")
    b["tactic"]["tactic_text"] = "A completely different tactic: a back five with wing-backs pressing high and a lone striker."
    place(pr.dir, "brief", b)
    machine.begin(pr, "intake")
    machine.submit(pr, "intake")
    assert machine.status(pr, "intake").status == "completed"
    st = machine.status(pr, "tactic")
    assert st.status == "stale" and "brief" in st.reason
    with pytest.raises(GateViolation, match="QR-01"):  # old review was bound to the old brief
        machine.submit(pr, "tactic")
    machine.record_qa(pr, "tactic", "tactics-critic", review("tactic", "tactics-critic"))
    assert machine.submit(pr, "tactic")["status"] == "awaiting_human"  # the old approval does NOT carry over


# --- finding 2: rounds per epoch ----------------------------------------------------------------
def test_review_rounds_reset_after_each_rejection(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    tactic_awaiting(pr)
    for i in range(4):
        approve_flow.handle_prompt(pr, f"reject tactic: change number {i}", "s")
        for _ in range(2):
            machine.record_qa(pr, "tactic", "tactics-critic", review("tactic", "tactics-critic", "fix_and_rereview"))
        machine.record_qa(pr, "tactic", "tactics-critic", review("tactic", "tactics-critic"))
        assert machine.submit(pr, "tactic")["status"] == "awaiting_human"


# --- finding 3: conditional approvals -----------------------------------------------------------
@pytest.mark.parametrize("msg", ["approve tactic? not sure yet", "approve tactic once the critic re-checks the shape",
                                 "approve tactic but change the colours", "approve tactic and storyboard"])
def test_conditional_messages_are_not_approvals(msg, tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    tactic_awaiting(pr)
    out = approve_flow.handle_prompt(pr, msg, "s")
    assert "NOT RECORDED" in out
    assert machine.status(pr, "tactic").status == "awaiting_human"
    assert pr.records("approvals") == []


@pytest.mark.parametrize("msg", ["approve tactic", "  Approve Tactic.  ", "approve tactic!"])
def test_explicit_approvals_are_recorded(msg, tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    tactic_awaiting(pr)
    assert "APPROVAL RECORDED" in approve_flow.handle_prompt(pr, msg, "s")


# --- finding 4: long rejection ------------------------------------------------------------------
def test_long_rejection_is_fully_recorded(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    tactic_awaiting(pr)
    out = approve_flow.handle_prompt(pr, "reject tactic: " + "wider fullbacks please. " * 60, "s")
    assert "REJECTION RECORDED" in out
    assert pr.records("decisions")[-1]["text"].startswith("rejected tactic")
    assert audit.audit(pr) == []


# --- finding 6: clean errors instead of tracebacks ------------------------------------------------
def test_unknown_or_wrong_mode_stage_errors_cleanly(tmp_projects):
    pr = make(tmp_projects)
    for bad in ("research", "storybaord"):
        with pytest.raises(ProjectError, match="not part of mode"):
            machine.begin(pr, bad)
    with pytest.raises(ProjectError):
        machine.record_qa(pr, "bogus", "tactics-critic", review("bogus", "tactics-critic"))


def test_non_utf8_artifact_does_not_crash_status(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    pr.artifact_path("brief").write_bytes(json.dumps(fixture("brief")).replace("Reds", "Réds").encode("cp1252"))
    assert machine.status(pr, "intake").status == "stale"


def test_corrupt_state_line_is_reported_not_crashed(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    with open(pr.record_file("events"), "a", encoding="utf-8") as f:
        f.write('{"ts": "2026-11-02T12:00:00Z", "type": "beg\n')
    with pytest.raises(ProjectError, match="corrupt"):
        machine.status(pr, "intake")
    assert any("corrupt" in p for p in audit.audit(pr))


def test_audit_survives_schema_invalid_qa_record(tmp_projects):
    pr = make(tmp_projects)
    with open(pr.record_file("qa"), "a", encoding="utf-8") as f:
        f.write('{"id": "Q-001"}\n')
    probs = audit.audit(pr)
    assert any(p.startswith("qa[0]") for p in probs)


# --- finding 7: tests that bite ---------------------------------------------------------------------
def _approved(tmp_projects, slug="fx-ifb-442"):
    pr = make(tmp_projects, slug)
    intake(pr, dict(fixture("brief"), project_id=slug))
    tactic_awaiting(pr)
    approve_flow.approve(pr, "tactic", "test", "t")
    return pr


def test_signature_is_what_makes_an_approval_valid(tmp_projects):
    pr = _approved(tmp_projects)
    f = pr.record_file("approvals")
    rec = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
    rec["nonce"] = "f" * 32  # stage + hashes still match; only the seal is now wrong
    f.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert machine.status(pr, "tactic").status == "awaiting_human"
    assert any("bad signature" in p or "seal invalid" in p for p in audit.audit(pr))


def test_approval_replayed_from_another_project_is_rejected(tmp_projects):
    a = _approved(tmp_projects, "proj-a")
    b = make(tmp_projects, "proj-b")
    intake(b, dict(fixture("brief"), project_id="proj-b"))
    tactic_awaiting(b)
    line = a.record_file("approvals").read_text(encoding="utf-8")
    with open(b.record_file("approvals"), "a", encoding="utf-8") as f:
        f.write(line)
    assert machine.status(b, "tactic").status == "awaiting_human"
    assert any("another project" in p for p in audit.audit(b))


def test_rotating_the_key_invalidates_old_approvals(tmp_projects, tmp_path, monkeypatch):
    pr = _approved(tmp_projects)
    monkeypatch.setenv("TMS_KEY_DIR", str(tmp_path / "other-keys"))
    assert machine.status(pr, "tactic").status == "awaiting_human"


def test_hand_written_event_is_detected(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    ev = json.loads(pr.record_file("events").read_text(encoding="utf-8").splitlines()[0])
    ev["stage"] = "tactic"
    with open(pr.record_file("events"), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
    assert any("seal invalid" in p for p in audit.audit(pr))


def test_altered_review_file_is_detected(tmp_projects):
    pr = make(tmp_projects)
    intake(pr)
    tactic_awaiting(pr)
    rec = pr.records("qa")[0]
    (pr.dir / rec["file"]).write_text(json.dumps(review("tactic", "tactics-critic") | {"summary": "rewritten afterwards by someone"}),
                                      encoding="utf-8")
    assert any("altered" in p for p in audit.audit(pr))


def test_default_key_dir_is_outside_the_repo(monkeypatch):
    monkeypatch.delenv("TMS_KEY_DIR", raising=False)
    assert approvals.key_dir() == approvals.default_key_dir()
    assert not str(approvals.default_key_dir().resolve()).lower().startswith(str(paths.root().resolve()).lower())


def test_tests_do_not_touch_the_real_scratch_dir():
    assert os.environ["TMS_SCRATCH_DIR"] and paths.scratch_dir() != paths.root() / ".tms"


def test_reopening_upstream_without_changes_makes_downstream_stale(tmp_projects):
    pr = _approved(tmp_projects)
    assert machine.status(pr, "tactic").status == "completed"
    machine.begin(pr, "intake")  # reopen: files unchanged, but intake is no longer completed
    st = machine.status(pr, "tactic")
    assert st.status == "stale" and "upstream" in st.reason


def test_key_rotation_is_diagnosed_precisely(tmp_projects, tmp_path, monkeypatch):
    pr = _approved(tmp_projects)
    monkeypatch.setenv("TMS_KEY_DIR", str(tmp_path / "rotated"))
    assert any("different key" in p for p in audit.audit(pr))
