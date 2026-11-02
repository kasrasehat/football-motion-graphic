"""Minimal .env loader. Values are returned to callers but never printed or logged."""
from __future__ import annotations

import os
from pathlib import Path

from tms import paths

SECRET_KEYS = ("ELEVENLABS_API_KEY", "API_FOOTBALL_KEY")


def load(path: Path | None = None) -> dict[str, str]:
    p = path or paths.root() / ".env"
    out: dict[str, str] = {}
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def get(name: str, default: str = "") -> str:
    """Process env wins over .env (lets tests and CI inject values)."""
    if name in os.environ:
        return os.environ[name]
    return load().get(name, default)


def present(name: str) -> bool:
    return bool(get(name).strip())
