"""`tms verify` — the single "is everything green?" command (development gate)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time

from tms import paths


def _steps(fast: bool) -> list[tuple[str, list[str]]]:
    py = str(paths.venv_python())
    npm = shutil.which("npm") or "npm"
    marker = "fast" if fast else "not live"
    steps = [
        ("harness mirrors", [py, "-m", "tms", "sync-harness", "--check"]),
        (f"pytest ({marker})", [py, "-m", "pytest", "-m", marker, "-q", "-p", "no:cacheprovider"]),
    ]
    if (paths.render_dir() / "test").is_dir() and any((paths.render_dir() / "test").glob("*.test.ts")):
        steps.append(("render verify", [npm, "--prefix", str(paths.render_dir()), "run", "verify:fast" if fast else "verify"]))
    return steps


def cmd_verify(args) -> int:
    failed = []
    for name, argv in _steps(args.fast):
        t0 = time.perf_counter()
        p = subprocess.run(argv, cwd=paths.root(), capture_output=True, text=True, encoding="utf-8", errors="replace")
        dt = time.perf_counter() - t0
        ok = p.returncode == 0
        print(f"[{'PASS' if ok else 'FAIL'}] {name} ({dt:.1f}s)")
        if not ok:
            failed.append(name)
            tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-30:])
            print("    " + tail.replace("\n", "\n    "), file=sys.stdout)
    print("verify: " + ("GREEN" if not failed else f"RED ({', '.join(failed)})"))
    return 1 if failed else 0


def register(sub) -> None:
    p = sub.add_parser("verify", help="run every check: harness sync, pytest (excluding live), renderer verify")
    p.add_argument("--fast", action="store_true", help="only tests marked fast + typecheck")
    p.set_defaults(func=cmd_verify)
