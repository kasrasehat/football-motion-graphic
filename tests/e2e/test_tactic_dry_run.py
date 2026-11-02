"""M7 offline end-to-end: the full tactic pipeline with mock providers, real gates, real renders (scale 0.5).
Approvals use the test channel (dry runs only) and QA reviews are fixtures — everything else is the real chain."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tms import paths
from tms.state import approve_flow, audit, machine, project as P
from tests.helpers import fixture, place

pytestmark = pytest.mark.e2e


def review(stage, agent):
    r = fixture("qa_review")
    r.update(stage=stage, agent=agent)
    return r


def cli(*args, env):
    return subprocess.run([sys.executable, "-m", "tms", *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=paths.root())


def test_tactic_pipeline_end_to_end(tmp_projects):
    env = dict(os.environ)
    pr = P.init("fx-ifb-442", "tactic", "E2E", dry_run=True)
    # intake
    machine.begin(pr, "intake")
    place(pr.dir, "brief", fixture("brief"))
    assert machine.submit(pr, "intake")["status"] == "completed"
    # tactic
    machine.begin(pr, "tactic")
    place(pr.dir, "tactic_spec", fixture("tactic_spec"))
    assert cli("tactic", "still", "-p", pr.id, env=env).returncode == 0
    assert (pr.dir / "renders" / "tactic_still.png").stat().st_size > 10_000
    machine.record_qa(pr, "tactic", "tactics-critic", review("tactic", "tactics-critic"))
    assert machine.submit(pr, "tactic")["status"] == "awaiting_human"
    approve_flow.approve(pr, "tactic", "test", "e2e")
    # storyboard
    machine.begin(pr, "storyboard")
    place(pr.dir, "scene_plan", fixture("scene_plan"))
    place(pr.dir, "narration_script", fixture("narration_script"))
    r = cli("storyboard", "compile", "-p", pr.id, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    for agent in ("tactics-critic", "script-editor", "visual-qa"):
        machine.record_qa(pr, "storyboard", agent, review("storyboard", agent))
    assert machine.submit(pr, "storyboard")["status"] == "awaiting_human"
    approve_flow.approve(pr, "storyboard", "test", "e2e")
    # audio
    machine.begin(pr, "audio")
    r = cli("audio", "build", "-p", pr.id, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert machine.submit(pr, "audio")["status"] == "completed"
    # render
    machine.begin(pr, "render")
    r = cli("render", "final", "-p", pr.id, "--scale", "0.5", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = pr.load_artifact("render_report")
    assert rep["verdict"] == "pass"
    assert {c["rule"] for c in rep["checks"] if c["ok"]} >= {"FQ-01", "FQ-02", "FQ-03", "FQ-04", "FQ-05", "FQ-06"}
    assert (pr.dir / "renders" / "captions.srt").read_text(encoding="utf-8").startswith("1\n")
    machine.record_qa(pr, "render", "visual-qa", review("render", "visual-qa"))
    assert machine.submit(pr, "render")["status"] == "awaiting_human"
    approve_flow.approve(pr, "final", "test", "e2e")
    assert machine.next_stage(pr) is None, [s.as_dict() for s in machine.all_status(pr)]
    assert audit.audit(pr) == []

    # negative: changing the storyboard after approval makes everything downstream stale and blocks rendering
    plan = fixture("scene_plan")
    plan["scenes"][0]["title"] = "Changed after approval"
    place(pr.dir, "scene_plan", plan)
    assert machine.status(pr, "storyboard").status == "stale"
    assert machine.status(pr, "render").status == "stale"
    r = cli("render", "final", "-p", pr.id, "--scale", "0.5", env=env)
    assert r.returncode == 2 and "upstream not completed" in r.stderr
