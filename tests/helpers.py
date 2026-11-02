"""Test helpers shared across suites."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from tms import jsonio
from tms.validate import validate_doc
from tms.validate.registry import Context

FIX = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str) -> Any:
    return copy.deepcopy(json.loads((FIX / "artifacts" / f"{name}.json").read_text(encoding="utf-8")))


def findings(artifact: str, doc: Any, ctx: Context | None = None):
    return validate_doc(artifact, doc, ctx or Context())


def rule_ids(artifact: str, doc: Any, ctx: Context | None = None, severity: str | None = None) -> set[str]:
    return {f.rule for f in findings(artifact, doc, ctx) if severity is None or f.severity == severity}


def expect_violation(rule_id: str, artifact: str, doc: Any, ctx: Context | None = None) -> None:
    """Negative test: the mutated doc must trigger rule_id (and still be schema-valid)."""
    fs = findings(artifact, doc, ctx)
    schema_errs = [f for f in fs if f.rule == "SCHEMA"]
    assert not schema_errs, f"mutation for {rule_id} broke the schema instead: {schema_errs[:3]}"
    assert rule_id in {f.rule for f in fs}, f"{rule_id} did not fire; got {[(f.rule, f.message) for f in fs]}"


def expect_clean(artifact: str, doc: Any, ctx: Context | None = None) -> None:
    errs = [f for f in findings(artifact, doc, ctx) if f.severity == "error"]
    assert not errs, [(f.rule, f.location, f.message) for f in errs]


def place(project_dir: Path, name: str, doc: Any) -> Path:
    from tms import manifest
    p = manifest.artifact_path(project_dir, name)
    jsonio.write_json(p, doc)
    return p


def copy_media(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
