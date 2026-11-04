"""Shared CLI plumbing: --project option, uniform error handling, JSON output."""
from __future__ import annotations

import functools
import json
import sys

from tms.state.project import GateViolation, ProjectError


def add_project_arg(p) -> None:
    p.add_argument("--project", "-p", metavar="SLUG", help="project slug (default: this session's project)")


def handled(fn):
    @functools.wraps(fn)
    def wrapper(args):
        try:
            return fn(args) or 0
        except GateViolation as e:
            print(f"GATE: {e}", file=sys.stderr)
            return 2
        except ProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except FileNotFoundError as e:
            print(f"ERROR: file not found: {e.filename or e}", file=sys.stderr)
            return 1
    return wrapper


def emit(doc, as_json: bool, text: str | None = None) -> None:
    if as_json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print(text if text is not None else json.dumps(doc, indent=2, ensure_ascii=False))
