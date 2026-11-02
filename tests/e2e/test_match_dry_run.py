"""M10 offline end-to-end: a full match preview (fx-match) — research from a cassette + web claims, analysis with
the engine prediction, data-graphic storyboard, mock audio, final render — through every real gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tms import jsonio, paths
from tms.research import api_football as AF
from tms.state import approve_flow, audit, machine, project as P
from tests.fixtures.match.make_match_fixtures import CassetteClient, cassette
from tests.helpers import FIX, fixture, place

pytestmark = pytest.mark.e2e
M = FIX / "match"


def review(stage, agent):
    r = fixture("qa_review")
    r.update(stage=stage, agent=agent)
    return r


def cli(*args):
    return subprocess.run([sys.executable, "-m", "tms", *args], capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ), cwd=paths.root())


def load(name):
    return json.loads((M / f"{name}.json").read_text(encoding="utf-8"))


def _restamp(claims: list[dict], now) -> None:
    """Simulate research done just now: retrieval 15 min ago, dated facts 2 h ago (keeps the test valid on any day)."""
    from datetime import timedelta
    iso = lambda t: t.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for c in claims:
        if c.get("as_of"):
            c["as_of"] = iso(now - timedelta(hours=2))
        for s in c["sources"]:
            s["retrieved_at"] = iso(now - timedelta(minutes=15))


def test_match_preview_end_to_end(tmp_projects, monkeypatch):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    pr = P.init("fx-match", "match_preview", "Real Madrid v Arsenal", dry_run=True)
    machine.begin(pr, "intake")
    place(pr.dir, "brief", fixture("brief.match"))
    assert machine.submit(pr, "intake")["status"] == "completed"

    # research: API bundle from the cassette (no key/network in tests) + web claims, merged with a pinned clock
    machine.begin(pr, "research")
    claims, _ = AF.pull(CassetteClient(cassette()), 1234567, "2026-11-02T12:10:00Z")
    _restamp(claims, now)
    jsonio.write_json(pr.dir / "media" / "research" / "api_claims.json", {"claims": claims, "pulled_at": jsonio.now_iso()})
    web = fixture("web_claims")
    _restamp(web["claims"], now)
    web["runs"] = [dict(r, finished_at=jsonio.now_iso()) for r in web["runs"]]
    place(pr.dir, "web_claims", web)
    import tms.research.cli as RC
    findings = RC.build(pr)
    assert not [f for f in findings if f.severity == "error"], [(f.rule, f.message) for f in findings]
    machine.record_qa(pr, "research", "fact-checker", review("research", "fact-checker"))
    assert machine.submit(pr, "research")["status"] == "completed"

    # analysis: analyst artifacts + engine prediction
    machine.begin(pr, "analysis")
    place(pr.dir, "match_analysis", fixture("match_analysis"))
    place(pr.dir, "tactic_spec", load("tactic_spec"))
    r = cli("predict", "build", "-p", pr.id)
    assert r.returncode == 0, r.stdout + r.stderr
    pred = pr.load_artifact("prediction")
    assert abs(sum(pred["probs_final"].values()) - 1) < 1e-3
    for agent in ("tactics-critic", "fact-checker"):
        machine.record_qa(pr, "analysis", agent, review("analysis", agent))
    assert machine.submit(pr, "analysis")["status"] == "awaiting_human"
    approve_flow.approve(pr, "analysis", "test", "e2e")

    # storyboard: graphics bound to dossier/prediction + two animated battles
    machine.begin(pr, "storyboard")
    place(pr.dir, "scene_plan", load("scene_plan"))
    narration = load("narration_script")
    for n, p_ in (("47%", "home"), ("26%", "draw"), ("27%", "away")):  # keep spoken percentages true to the engine's numbers
        val = round(pred["probs_final"][p_] * 100)
        line = next(ln for ln in narration["lines"] if ln["scene"] == "S09")
        line["text"] = line["text"].replace(n, f"{val}%")
        for num in line["numbers"]:
            if num["text"] == n:
                num["text"] = f"{val}%"
    place(pr.dir, "narration_script", narration)
    r = cli("storyboard", "compile", "-p", pr.id)
    assert r.returncode == 0, r.stdout + r.stderr
    r = cli("validate", "scene_plan", "narration_script", "-p", pr.id)
    assert r.returncode == 0, r.stdout + r.stderr
    for agent in ("tactics-critic", "script-editor", "visual-qa", "fact-checker"):
        machine.record_qa(pr, "storyboard", agent, review("storyboard", agent))
    assert machine.submit(pr, "storyboard")["status"] == "awaiting_human"
    approve_flow.approve(pr, "storyboard", "test", "e2e")

    # audio + render
    machine.begin(pr, "audio")
    r = cli("audio", "build", "-p", pr.id)
    assert r.returncode == 0, r.stdout + r.stderr
    assert machine.submit(pr, "audio")["status"] == "completed"
    machine.begin(pr, "render")
    r = cli("render", "final", "-p", pr.id, "--scale", "0.5")
    assert r.returncode == 0, r.stdout + r.stderr
    rep = pr.load_artifact("render_report")
    assert rep["verdict"] == "pass"
    props = pr.load_artifact("render_props")
    templates = {g["template"] for g in props["graphics"]}
    assert {"form_guide", "stat_compare", "lineup_board", "probability_bar", "prediction_card"} <= templates
    pb = next(g for g in props["graphics"] if g["template"] == "probability_bar")["data"]
    assert pb == {k: pred["probs_final"][k] for k in ("home", "draw", "away")}  # graphics carry engine numbers, not typed ones
    machine.record_qa(pr, "render", "visual-qa", review("render", "visual-qa"))
    machine.submit(pr, "render")
    approve_flow.approve(pr, "final", "test", "e2e")
    assert machine.next_stage(pr) is None
    assert audit.audit(pr) == []
