"""M4/M5 command-level tests (no rendering): still props, draft compile, props-only preview."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tms import jsonio, paths, schema
from tms.choreo.cli import preview
from tms.state import approve_flow, machine, project as P
from tms.tactic.still import still_props
from tests.helpers import fixture, place

pytestmark = pytest.mark.fast


@pytest.mark.parametrize("aspect", ["16:9", "9:16", "1:1"])
def test_still_props_schema_valid(aspect):
    b = fixture("brief")
    b["aspect"] = aspect
    props = still_props(fixture("tactic_spec"), b)
    assert schema.validate_artifact("render_props", props) == []
    assert props["camera"][2] >= 10500  # full pitch fits, never cropped


def _storyboard_project():
    pr = P.init("fx-ifb-442", "tactic", "t", dry_run=True)
    machine.begin(pr, "intake")
    place(pr.dir, "brief", fixture("brief"))
    machine.submit(pr, "intake")
    machine.begin(pr, "tactic")
    place(pr.dir, "tactic_spec", fixture("tactic_spec"))
    machine.record_qa(pr, "tactic", "tactics-critic", fixture("qa_review"))
    machine.submit(pr, "tactic")
    approve_flow.approve(pr, "tactic", "test", "t")
    machine.begin(pr, "storyboard")
    return pr


def test_draft_compile_writes_nothing(tmp_projects):
    pr = _storyboard_project()
    draft = pr.dir / "drafts" / "scene_plan.json"
    jsonio.write_json(draft, fixture("scene_plan"))
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-m", "tms", "storyboard", "compile", "--plan", str(draft), "-p", pr.id],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=paths.root())
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 error(s)" in r.stdout
    assert not pr.artifact_path("choreography").exists()


def test_preview_props_only(tmp_projects):
    pr = _storyboard_project()
    place(pr.dir, "scene_plan", fixture("scene_plan"))
    place(pr.dir, "narration_script", fixture("narration_script"))
    res = preview(pr, render=False)
    assert not [f for f in res["findings"] if f.severity == "error"]
    props = jsonio.read_json(res["props"])
    assert schema.validate_artifact("render_props", props) == []
    assert props["durationInFrames"] == res["frames"]
    assert len(props["camera"]) == 3 * res["frames"]
    assert all(len(v) == 2 * res["frames"] for v in props["tracks"]["players"].values())
    assert schema.validate_artifact("choreography", pr.load_artifact("choreography")) == []
