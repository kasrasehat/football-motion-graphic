"""Project folders, project.json, per-session project selection, record files.

Which project does a command without --project mean?
  * Inside a harness session (session id in the environment, or given by a hook payload): the project bound to THAT
    session by `tms init` / `tms use`. A session never follows another session's choice.
  * Outside any session (the user's own terminal): the terminal pointer set by `tms use`.
"""
from __future__ import annotations

import os
import re
import sys
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


# Shell-tool processes get the harness session id from these (first set wins). TMS_SESSION_ID is a manual override;
# CLAUDE_CODE_SESSION_ID matches the hook payload's session_id; CODEX_THREAD_ID is best effort, untested on Codex.
SESSION_VARS = ("TMS_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")


def current_session() -> str:
    for var in SESSION_VARS:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


def active_file() -> Path:
    """The terminal pointer: only commands running outside any session read or move it."""
    return paths.scratch_dir() / "active_project"


def _session_file(session_id: str) -> Path:
    d = paths.scratch_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d / re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)


def bound_slug(session_id: str) -> str | None:
    f = _session_file(session_id) if session_id else None
    return f.read_text(encoding="utf-8").strip() if f and f.is_file() else None


def all_slugs() -> list[str]:
    root = paths.projects_dir()
    return sorted(p.parent.name for p in root.glob("*/project.json")) if root.is_dir() else []


def set_active(slug: str) -> None:
    session = current_session()
    (_session_file(session) if session else active_file()).write_text(slug + "\n", encoding="utf-8")


def session_slug(session_id: str) -> str:
    """The project of a session; with no binding only a lone project is unambiguous. Never reads the terminal pointer."""
    bound = bound_slug(session_id)
    if bound:
        return bound
    slugs = all_slugs()
    if len(slugs) == 1:
        if session_id:
            _session_file(session_id).write_text(slugs[0] + "\n", encoding="utf-8")
        return slugs[0]
    if not slugs:
        raise ProjectError("no projects yet: run `tms init`")
    raise ProjectError("this session is not bound to a project: run `tms use <slug>` or pass --project <slug>. "
                       f"Projects: {', '.join(slugs)}")


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


def _terminal_slug() -> str:
    f = active_file()
    if not f.is_file():
        raise ProjectError("no active project: pass --project <slug> or run `tms init` / `tms use`")
    slug = f.read_text(encoding="utf-8").strip()
    if len(all_slugs()) > 1:  # stderr, so --json output on stdout stays parseable
        print(f"[tms] using project {slug} (terminal pointer); pass --project to choose another", file=sys.stderr)
    return slug


def load(slug: str | None = None) -> Project:
    if not slug:
        session = current_session()
        slug = session_slug(session) if session else _terminal_slug()
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
