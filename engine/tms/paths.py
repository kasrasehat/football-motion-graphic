"""Filesystem layout. Every path the engine touches is derived here."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def root() -> Path:
    """Repository root: the nearest ancestor of this file that holds pipeline.yaml or pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "engine").is_dir():
            return parent
    raise RuntimeError("cannot locate repository root")


def projects_dir() -> Path:
    override = os.environ.get("TMS_PROJECTS_DIR", "").strip()
    return Path(override).resolve() if override else root() / "projects"


def project_dir(slug: str) -> Path:
    return projects_dir() / slug


def config_dir() -> Path:
    return root() / "config"


def schemas_dir() -> Path:
    return root() / "schemas"


def render_dir() -> Path:
    return root() / "render"


def venv_python() -> Path:
    win = root() / ".venv" / "Scripts" / "python.exe"
    return win if win.exists() else root() / ".venv" / "bin" / "python"


def scratch_dir() -> Path:
    """Repo-local runtime dir for markers/active project/hook log (gitignored). Tests redirect it."""
    override = os.environ.get("TMS_SCRATCH_DIR", "").strip()
    d = Path(override) if override else root() / ".tms"
    d.mkdir(parents=True, exist_ok=True)
    return d
