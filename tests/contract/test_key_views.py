"""The approval key must be the same for every process of the user, whatever file-system view it runs in.

Measured on 2026-11-04: processes started by the packaged desktop app get a private overlay over %LOCALAPPDATA%.
Their writes land in %LOCALAPPDATA%\\Packages\\<app>\\LocalCache\\Local\\... and shadow the real path; a Terminal-panel
shell sees only the real path. %LOCALAPPDATA% has the same value in both. %USERPROFILE% is the same place in both.
Tests model the two views by pointing LOCALAPPDATA at different folders and sharing one home.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tms.harness import policy
from tms.state import approve_flow, approvals, audit, machine, project as P
from tms.state.project import ProjectError
from tests.helpers import fixture, place

pytestmark = pytest.mark.fast
APP = "TacticMotionStudio"
KEY = "approval.key"


class Views:
    def __init__(self, tmp: Path, monkeypatch):
        self.mp = monkeypatch
        self.home, self.real, self.overlay = tmp / "home", tmp / "Local", tmp / "overlay"
        for d in (self.home, self.real, self.overlay):
            d.mkdir()
        monkeypatch.delenv("TMS_KEY_DIR", raising=False)
        monkeypatch.setenv("USERPROFILE", str(self.home))
        monkeypatch.setenv("HOME", str(self.home))
        self.terminal()

    def terminal(self) -> None:
        self.mp.setenv("LOCALAPPDATA", str(self.real))

    def app(self) -> None:
        self.mp.setenv("LOCALAPPDATA", str(self.overlay))

    def plant_old_keys(self) -> None:
        """The state on the user's machine: one old key per view, the app's physically under Packages."""
        physical = self.real / "Packages" / "Claude_x" / "LocalCache" / "Local" / APP
        for folder, byte in ((self.real / APP, "aa"), (physical, "bb"), (self.overlay / APP, "bb")):
            folder.mkdir(parents=True)
            (folder / KEY).write_text(byte * 32, encoding="utf-8")


@pytest.fixture
def views(tmp_path, monkeypatch):
    return Views(tmp_path, monkeypatch)


def awaiting_tactic() -> P.Project:
    pr = P.init("fx-ifb-442", "tactic", "t", dry_run=True)
    machine.begin(pr, "intake")
    place(pr.dir, "brief", fixture("brief"))
    machine.submit(pr, "intake")
    machine.begin(pr, "tactic")
    place(pr.dir, "tactic_spec", fixture("tactic_spec"))
    machine.record_qa(pr, "tactic", "tactics-critic", fixture("qa_review"))
    machine.submit(pr, "tactic")
    return pr


def split_brain_project(views: Views) -> P.Project:
    """Reproduce the report: records sealed in the app's view, the user's approval signed in the Terminal's view."""
    views.plant_old_keys()
    views.app()
    pr = awaiting_tactic()
    views.terminal()
    approve_flow.approve(pr, "tactic", "tty", "terminal")
    return pr


def run_migrate(monkeypatch):
    monkeypatch.setattr(approve_flow, "_require_tty", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompt.split()[1])
    return approve_flow.migrate_keys_tty()


# --- the fault ---------------------------------------------------------------------------------------------
def test_new_install_has_one_key_across_views(views, tmp_projects):
    """Fails on a default key dir under LOCALAPPDATA: each view would mint its own key."""
    views.app()
    pr = awaiting_tactic()
    views.terminal()
    approve_flow.approve(pr, "tactic", "tty", "terminal")
    assert audit.audit(pr) == [] and machine.status(pr, "tactic").status == "completed"
    views.app()
    assert audit.audit(pr) == [] and machine.status(pr, "tactic").status == "completed"


def test_default_key_dir_is_not_under_appdata(views):
    assert views.real not in approvals.default_key_dir().parents
    assert approvals.default_key_dir().parent == views.home


def test_explicit_key_dir_is_isolated_from_old_keys(views, tmp_path, monkeypatch):
    """A redirected run (tests, manual experiments) must never find, and so never open or copy, the machine's real keys."""
    views.plant_old_keys()
    monkeypatch.setenv("TMS_KEY_DIR", str(tmp_path / "isolated"))
    assert approvals.old_key_files() == []
    run_migrate(monkeypatch)
    assert list((tmp_path / "isolated").glob("trusted/*")) == []


def test_key_status_lists_old_keys_without_opening_them(views):
    views.plant_old_keys()
    views.overlay.joinpath(APP, KEY).write_text("not hex", encoding="utf-8")
    views.real.joinpath(APP, KEY).write_text("not hex", encoding="utf-8")
    views.app()
    views.mp.setattr(approvals, "_signing_file", lambda: None)  # status of the signing key is not what this checks
    st = approvals.key_status()  # would raise if it parsed the unreadable files
    assert str(views.overlay / APP / KEY) in st["old_keys_found"]


# --- before migration nothing changes, and the split stays visible ---------------------------------------
def test_old_state_keeps_working_until_migrated_and_is_reported(views, tmp_projects, monkeypatch):
    pr = split_brain_project(views)
    views.app()
    assert machine.status(pr, "tactic").status == "awaiting_human"
    assert any("A-001" in p and "unknown key" in p and "tms key migrate" in p for p in audit.audit(pr))
    views.terminal()
    assert any("seal invalid" in p for p in audit.audit(pr))
    assert approvals.migration_pending()
    assert not (views.home / f".{APP}" / KEY).exists()


def test_reading_never_mints_a_key(views, tmp_projects):
    views.plant_old_keys()
    views.app()
    pr = awaiting_tactic()
    for f in (views.real / APP / KEY, views.overlay / APP / KEY,
              views.real / "Packages" / "Claude_x" / "LocalCache" / "Local" / APP / KEY):
        f.unlink()
    assert machine.status(pr, "tactic").status == "awaiting_human"
    audit.audit(pr)
    assert not (views.home / f".{APP}").exists()


def test_view_without_old_key_refuses_to_fork_a_third_one(views, tmp_projects):
    """A Terminal that sees no key at the real path must not silently start a new one while the app's still exists."""
    physical = views.real / "Packages" / "Claude_x" / "LocalCache" / "Local" / APP
    physical.mkdir(parents=True)
    (physical / KEY).write_text("bb" * 32, encoding="utf-8")
    with pytest.raises(ProjectError, match="tms key migrate"):
        approvals.seal({"x": 1})


# --- migration: the sanctioned answer for A-001 ----------------------------------------------------------
def test_migration_makes_the_real_approval_count_in_both_views_without_touching_records(views, tmp_projects, monkeypatch):
    pr = split_brain_project(views)
    state_before = {f.name: f.read_bytes() for f in pr.state_dir.glob("*.jsonl")}
    res = run_migrate(monkeypatch)
    assert len(res["imported"]) == 2
    assert {f.name: f.read_bytes() for f in pr.state_dir.glob("*.jsonl")} == state_before
    for view in (views.terminal, views.app):
        view()
        assert audit.audit(pr) == []
        st = machine.status(pr, "tactic")
        assert st.status == "completed" and st.approval["id"] == "A-001"
    assert not approvals.migration_pending()


def test_migration_is_idempotent_and_new_records_share_one_key(views, tmp_projects, monkeypatch):
    pr = split_brain_project(views)
    first = run_migrate(monkeypatch)
    assert run_migrate(monkeypatch)["imported"] == []
    views.app()
    kid = approvals.key_id()
    views.terminal()
    assert approvals.key_id() == kid == first["signing_key_id"]
    assert kid not in first["imported"]  # old keys are verify-only from now on
    machine.log_decision(pr, "process", "user", "after migration", None)
    views.app()
    assert audit.audit(pr) == []


def test_migration_requires_the_users_terminal(views):
    from tms.state.project import GateViolation
    with pytest.raises(GateViolation, match="interactive terminal"):
        approve_flow.migrate_keys_tty()


def test_migration_cancelled_by_a_wrong_code_changes_nothing(views, monkeypatch):
    from tms.state.project import GateViolation
    views.plant_old_keys()
    monkeypatch.setattr(approve_flow, "_require_tty", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "nope")
    with pytest.raises(GateViolation, match="cancelled"):
        approve_flow.migrate_keys_tty()
    assert not (views.home / f".{APP}").exists()


# --- tampering stays detectable --------------------------------------------------------------------------
def _edit_first(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_edited_records_are_still_caught_after_migration(views, tmp_projects, monkeypatch):
    pr = split_brain_project(views)
    run_migrate(monkeypatch)
    _edit_first(pr.record_file("approvals"), '"tty"', '"prompt-hook"')
    assert any("bad signature" in p for p in audit.audit(pr))
    assert machine.status(pr, "tactic").status == "awaiting_human"
    _edit_first(pr.record_file("events"), '"intake"', '"tactic"')
    assert any("seal invalid" in p for p in audit.audit(pr))


def test_forged_approval_with_an_outside_key_is_not_honoured(views, tmp_projects, monkeypatch):
    pr = split_brain_project(views)
    run_migrate(monkeypatch)
    rec = dict(pr.records("approvals")[0], id="A-002", key_id="f" * 12)
    import hashlib, hmac
    from tms import jsonio
    body = {k: v for k, v in rec.items() if k != "hmac"}
    rec["hmac"] = hmac.new(b"\x01" * 32, jsonio.canonical(body), hashlib.sha256).hexdigest()
    assert "unknown key" in approvals.verify(pr, rec)
    assert not approvals.seal_ok(rec)


def test_a_key_planted_at_the_old_path_after_migration_is_not_trusted(views, tmp_projects, monkeypatch):
    pr = split_brain_project(views)
    run_migrate(monkeypatch)
    (views.real / APP / KEY).write_text("cc" * 32, encoding="utf-8")
    assert "cc" * 6 not in approvals.key_status()["trusted"]
    assert len(approvals.key_status()["trusted"]) == 2
    forged_id = approvals.hashlib.sha256(bytes.fromhex("cc" * 32)).hexdigest()[:12]
    assert forged_id not in approvals.key_status()["trusted"]
    assert audit.audit(pr) == []


# --- the key directory stays off limits ------------------------------------------------------------------
def test_agents_are_kept_out_of_the_new_location():
    for p in (f"C:/Users/x/.{APP}/{KEY}", f"C:/Users/x/.{APP}/trusted/abc.key"):
        assert policy.check_read(p).deny and policy.check_write(p).deny
    assert policy.check_command(f"cat ~/.{APP}/trusted/abc.key").deny
    assert not policy.check_read("C:/Users/x/notes.txt").deny
