"""Artifact validation = JSON Schema + domain rules (config/rules.yaml)."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from tms import jsonio, manifest, schema
from tms.validate.registry import Context, Finding, run_rules


def load_all() -> None:
    """Import every tms.validate.*_rules module (each registers its @rule functions)."""
    import tms.validate as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.endswith("_rules"):
            importlib.import_module(f"tms.validate.{mod.name}")


def validate_doc(name: str, doc: Any, ctx: Context) -> list[Finding]:
    spec = manifest.artifact(name) if name in manifest.artifact_names() else None
    schema_name = spec.schema if spec else name
    errs = schema.validate_artifact(schema_name, doc)
    if errs:  # domain rules assume a schema-valid document
        return [Finding("SCHEMA", "error", e) for e in errs]
    load_all()
    return run_rules(name, doc, ctx)


def validate_file(project_dir: Path, name: str, mode: str | None = None) -> list[Finding]:
    p = manifest.artifact_path(project_dir, name)
    if not p.is_file():
        return [Finding("MISSING", "error", f"{p.relative_to(project_dir).as_posix()} does not exist")]
    try:
        doc = jsonio.read_json(p)
    except ValueError as e:
        return [Finding("JSON", "error", f"invalid JSON: {e}")]
    if mode is None:
        pj = Path(project_dir) / "project.json"
        mode = jsonio.read_json(pj)["mode"] if pj.is_file() else None
    return validate_doc(name, doc, Context(project_dir=Path(project_dir), mode=mode))


def errors_only(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "error"]
