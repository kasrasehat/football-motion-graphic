"""Tactic Motion Studio engine (`tms`)."""
import sys

if sys.version_info < (3, 12):  # plain `python` on this machine is 3.8 — never use it
    raise SystemExit("tms requires Python >= 3.12. Use .venv/Scripts/tms (the project venv).")

__version__ = "0.1.0"
