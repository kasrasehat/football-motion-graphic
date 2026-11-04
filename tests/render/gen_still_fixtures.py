"""Regenerates tests/fixtures/still/props.<orientation>.json from the dense spec next to them, so the renderer's vitests
check what the engine really emits (tests/engine/test_tactic_still.py fails when these go stale).

Run: .venv/Scripts/python.exe tests/render/gen_still_fixtures.py
"""
from __future__ import annotations

import json
from pathlib import Path

from tms import jsonio
from tms.tactic.still import still_props

STILL = Path(__file__).resolve().parents[1] / "fixtures" / "still"
ASPECTS = {"landscape": "16:9", "portrait": "9:16", "square": "1:1"}


def dense_props(orientation: str, scale: float = 1.0) -> dict:
    spec = json.loads((STILL / "tactic_spec.json").read_text(encoding="utf-8"))
    brief = json.loads((STILL / "brief.json").read_text(encoding="utf-8"))
    return still_props(spec, {**brief, "aspect": ASPECTS[orientation]}, scale)


if __name__ == "__main__":
    for name in ASPECTS:
        jsonio.write_json(STILL / f"props.{name}.json", dense_props(name), compact=True)
        print(f"wrote props.{name}.json")
