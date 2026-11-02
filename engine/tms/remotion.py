"""Invoking the Remotion renderer (render/scripts/render.mjs) from Python."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from tms import envfile, paths

SYSTEM_BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def browser_executable() -> str:
    """Explicit TMS_BROWSER_EXECUTABLE wins; otherwise the first installed system Chrome/Edge.
    Remotion's own headless-shell download is geo-blocked from this machine (HTTP 403)."""
    explicit = envfile.get("TMS_BROWSER_EXECUTABLE").strip()
    if explicit:
        return explicit
    for cand in SYSTEM_BROWSERS:
        if Path(cand).is_file():
            return cand
    return ""


def node_env() -> dict[str, str]:
    env = dict(os.environ)
    exe = browser_executable()
    if exe:
        env["TMS_BROWSER_EXECUTABLE"] = exe
    return env


def render(composition: str, out: Path, props: Path | None = None, *, scale: float = 1.0,
           frames: tuple[int, int] | None = None, still: int | None = None, timeout: float = 3600) -> dict:
    """Run a render. Returns the final JSON line printed by render.mjs. Raises on failure."""
    argv = [shutil.which("node") or "node", "scripts/render.mjs", "--composition", composition,
            "--out", str(Path(out).resolve()), "--json-progress", "false", "--scale", str(scale)]
    if props is not None:
        argv += ["--props", str(Path(props).resolve())]
    if frames is not None:
        argv += ["--frames", f"{frames[0]}-{frames[1]}"]
    if still is not None:
        argv += ["--still", str(still)]
    p = subprocess.run(argv, cwd=paths.render_dir(), env=node_env(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"remotion render failed ({p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
    last = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
    return json.loads(last[-1]) if last else {}
