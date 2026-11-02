"""M0: bootstrap invariants — venv interpreter, env loading, CLI wiring, toolchain."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tms import cli, doctor, envfile, paths


@pytest.mark.fast
def test_runs_from_project_venv():
    assert sys.version_info >= (3, 12)
    assert Path(sys.prefix).resolve() == (paths.root() / ".venv").resolve()


@pytest.mark.fast
def test_root_detection():
    assert (paths.root() / "pyproject.toml").is_file()
    assert paths.render_dir().name == "render"


@pytest.mark.fast
def test_envfile_parsing(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# comment\nA=1\nB="quoted value"\n  C = spaced \nnot a pair\nEMPTY=\n', encoding="utf-8")
    d = envfile.load(f)
    assert d == {"A": "1", "B": "quoted value", "C": "spaced", "EMPTY": ""}


@pytest.mark.fast
def test_process_env_overrides_dotenv(monkeypatch):
    monkeypatch.setenv("TMS_SOME_TEST_VAR", "from-env")
    assert envfile.get("TMS_SOME_TEST_VAR") == "from-env"


@pytest.mark.fast
def test_projects_dir_override(tmp_projects):
    assert paths.projects_dir() == tmp_projects.resolve()


@pytest.mark.fast
def test_cli_registers_doctor():
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    assert "doctor" in sub.choices


@pytest.mark.fast
def test_gitignore_protects_secrets():
    gi = (paths.root() / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi.splitlines()
    assert ".claude/settings.local.json" in gi
    assert ".claude/settings.json" not in [ln.strip() for ln in gi.splitlines()]


def test_doctor_quick_has_no_errors():
    rep = doctor.run_doctor(quick=True)
    errors = [c for c in rep.checks if c["level"] == "error"]
    assert not errors, errors
