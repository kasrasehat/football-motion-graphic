"""Pure policy functions used by the hooks. No I/O beyond reading config/protected_paths.yaml."""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

import yaml

from tms import paths


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((paths.config_dir() / "protected_paths.yaml").read_text(encoding="utf-8"))


def rel_posix(p: str | Path) -> str | None:
    """Repo-relative POSIX path, or None if outside the repo."""
    raw = str(p).strip().strip('"').strip("'")
    if not raw:
        return None
    # Git-Bash style /e/foo -> E:/foo
    m = re.match(r"^/([a-zA-Z])/(.*)$", raw)
    if m:
        raw = f"{m.group(1)}:/{m.group(2)}"
    path = Path(raw)
    if not path.is_absolute():
        path = paths.root() / path
    try:
        return PurePosixPath(path.resolve().relative_to(paths.root().resolve()).as_posix()).as_posix()
    except ValueError:
        return None


def _glob_match(rel: str, pattern: str) -> bool:
    # fnmatch's * crosses '/', which is what we want for "**"; for a single "*" segment be strict.
    if "**" in pattern:
        return fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(rel, pattern.replace("/**", ""))
    return fnmatch.fnmatchcase(rel, pattern) and rel.count("/") == pattern.count("/")


@dataclass
class Verdict:
    deny: bool
    reason: str = ""


def check_write(p: str | Path) -> Verdict:
    rel = rel_posix(p)
    if rel is None:
        return Verdict(False)
    for rule in config()["deny_write"]:
        if _glob_match(rel, rule["pattern"]):
            return Verdict(True, f"{rel}: {rule['why']}")
    return Verdict(False)


def check_read(p: str | Path) -> Verdict:
    rel = rel_posix(p)
    if rel is None:
        return Verdict(False)
    for rule in config()["deny_read"]:
        if _glob_match(rel, rule["pattern"]):
            return Verdict(True, f"{rel}: {rule['why']}")
    return Verdict(False)


def check_command(cmd: str) -> Verdict:
    c = config()
    for rule in c["deny_commands"]:
        if re.search(rule["regex"], cmd):
            return Verdict(True, rule["why"])
    if re.search(c["protected_write_paths_regex"], cmd) and re.search(c["write_verbs_regex"], cmd):
        return Verdict(True, "shell writes into protected project state (state/, history/, build/, project.json) "
                             "are not allowed; use tms commands")
    return Verdict(False)


def dirty_kind(p: str | Path) -> str | None:
    rel = rel_posix(p)
    if rel is None:
        return None
    for kind, patterns in config()["dirty_paths"].items():
        if any(_glob_match(rel, pat) for pat in patterns):
            return kind
    return None


PATCH_HEADER = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.+?)\s*$", re.M)


def patch_paths(patch_text: str) -> list[str]:
    """File paths touched by a Codex apply_patch payload."""
    return [m.group(2) for m in PATCH_HEADER.finditer(patch_text or "")]
