"""Project folders, project.json, active-project selection, record files."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tms import jsonio, manifest, paths, schema

SUBDIRS = ("artifacts", "build", "media", "state", "history", "reviews", "renders")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class ProjectError(Exception):
    """User-facing error; exit code 1."""


class GateViolation(Exception):
    """Refused by a gate; exit code 2."""


@dataclass
class Project:
    dir: Path
    meta: dict

    @property
    def id(self) -> str:
        return self.meta["project_id"]

    @property
    def mode(self) -> str:
        return self.meta["mode"]

    @property
    def dry_run(self) -> bool:
        return bool(self.meta["dry_run"])

    @property
    def state_dir(self) -> Path:
        return self.dir / "state"

    def record_file(self, kind: str) -> Path:
        return self.state_dir / f"{kind}.jsonl"

    def records(self, kind: str) -> list[dict]:
        try:
            return list(jsonio.read_jsonl(self.record_file(kind)))
        except jsonio.CorruptRecord as e:
            raise ProjectError(f"state file corrupt: {e} — run `tms audit`; do not hand-edit state/") from e

    def artifact_path(self, name: str) -> Path:
        return manifest.artifact_path(self.dir, name)

    def load_artifact(self, name: str) -> dict | None:
        p = self.artifact_path(name)
        return jsonio.read_json(p) if p.is_file() else None

    def stages(self) -> list[str]:
        return manifest.mode_stages(self.mode)


def active_file() -> Path:
    return paths.scratch_dir() / "active_project"


def set_active(slug: str) -> None:
    active_file().write_text(slug + "\n", encoding="utf-8")


def init(slug: str, mode: str, title: str, dry_run: bool) -> Project:
    if not SLUG.match(slug):
        raise ProjectError(f"invalid slug {slug!r}: lowercase letters, digits, hyphens")
    if mode not in manifest.modes():
        raise ProjectError(f"unknown mode {mode!r}; choose from {manifest.modes()}")
    pdir = paths.project_dir(slug)
    if (pdir / "project.json").exists():
        raise ProjectError(f"project {slug} already exists")
    for d in SUBDIRS:
        (pdir / d).mkdir(parents=True, exist_ok=True)
    meta = {"version": "1", "project_id": slug, "mode": mode, "title": title, "created_at": jsonio.now_iso(),
            "dry_run": dry_run, "pipeline_version": "1"}
    errs = schema.errors(schema.state_validator("project"), meta)
    if errs:
        raise ProjectError("; ".join(errs))
    jsonio.write_json(pdir / "project.json", meta)
    set_active(slug)
    return Project(pdir, meta)


def load(slug: str | None = None) -> Project:
    if not slug:
        f = active_file()
        if not f.is_file():
            raise ProjectError("no active project: pass --project <slug> or run `tms init` / `tms use`")
        slug = f.read_text(encoding="utf-8").strip()
    pdir = paths.project_dir(slug)
    pj = pdir / "project.json"
    if not pj.is_file():
        raise ProjectError(f"project {slug!r} not found under {paths.projects_dir()}")
    return Project(pdir, jsonio.read_json(pj))


def next_id(records: list[dict], prefix: str) -> str:
    n = 0
    for r in records:
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", r.get("id", ""))
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:03d}"
