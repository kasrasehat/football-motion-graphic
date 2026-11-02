"""Subprocess helpers. Always argv lists (shell=False): the repo path contains spaces."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    code: int
    out: str
    err: str


def run(argv: list[str], cwd: Path | None = None, timeout: float | None = None, input: str | None = None) -> Result:
    exe = argv[0]
    resolved = shutil.which(exe) or exe  # resolves npx -> npx.cmd on Windows
    p = subprocess.run(
        [resolved, *argv[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, input=input,
    )
    return Result(p.returncode, p.stdout, p.stderr)
