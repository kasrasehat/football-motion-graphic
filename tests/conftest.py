"""Shared pytest fixtures. Tests never touch the real projects/ dir, .tms/ scratch dir, or the real approval key."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path, monkeypatch):
    """Every test gets its own scratch dir (active project, dirty marker, hook log) and approval key dir."""
    monkeypatch.setenv("TMS_SCRATCH_DIR", str(tmp_path / "scratch"))
    monkeypatch.setenv("TMS_KEY_DIR", str(tmp_path / "keys"))
    # The suite is often launched from inside a harness session; its identity must not leak into the tests.
    for var in ("TMS_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    """Redirect TMS_PROJECTS_DIR into tmp_path."""
    pdir = tmp_path / "projects"
    pdir.mkdir()
    monkeypatch.setenv("TMS_PROJECTS_DIR", str(pdir))
    return pdir


@pytest.fixture
def fixture_project(tmp_projects):
    """Copy a fixture project into the temp projects dir and return its path."""

    def _copy(name: str) -> Path:
        src = FIXTURES / "projects" / name
        dst = tmp_projects / name
        shutil.copytree(src, dst)
        return dst

    return _copy
