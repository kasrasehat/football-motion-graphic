"""`tms` command-line entry point. Subcommand modules expose register(subparsers)."""
from __future__ import annotations

import argparse
import importlib
import sys

# Order defines --help order. Each module registers one or more subcommands.
COMMAND_MODULES = [
    "tms.commands.state_cmds",
    "tms.commands.intake",
    "tms.tactic.cli",
    "tms.predict.cli",
    "tms.choreo.cli",
    "tms.audio.cli",
    "tms.render.cli",
    "tms.research.cli",
    "tms.commands.package",
    "tms.harness.sync",
    "tms.commands.verify",
    "tms.doctor",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tms", description="Tactic Motion Studio pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMAND_MODULES:
        importlib.import_module(name).register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)
