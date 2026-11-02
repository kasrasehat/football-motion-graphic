"""Rule registry. Every rule id lives in config/rules.yaml (severity, text, params) and is implemented
by exactly one function decorated with @rule. Rule functions yield findings; they never raise for bad data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from tms import paths


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # "error" | "warning"
    message: str
    location: str = ""

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "message": self.message, "location": self.location}


@dataclass
class Context:
    """What a rule may look at besides the artifact itself."""
    project_dir: Path | None = None
    mode: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)  # other artifacts already loaded, by name
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def other(self, name: str) -> Any:
        if name in self.artifacts:
            return self.artifacts[name]
        if self.project_dir is not None:
            from tms import jsonio, manifest
            p = manifest.artifact_path(self.project_dir, name)
            if p.is_file():
                self.artifacts[name] = jsonio.read_json(p)
                return self.artifacts[name]
        return None


RuleFn = Callable[[Any, Context, dict], Iterable["str | tuple[str, str] | tuple[str, str, str]"]]
_IMPL: dict[str, RuleFn] = {}


@lru_cache(maxsize=1)
def table() -> dict[str, dict]:
    """config/rules.yaml plus every config/rules.d/*.yaml (one file per rule family). Duplicate ids are an error."""
    files = [paths.config_dir() / "rules.yaml", *sorted((paths.config_dir() / "rules.d").glob("*.yaml"))]
    merged: dict[str, dict] = {}
    for f in files:
        if not f.is_file():
            continue
        for rid, meta in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("rules", {}).items():
            if rid in merged:
                raise RuntimeError(f"rule {rid} declared twice ({f.name})")
            merged[rid] = meta
    return merged


def params(rule_id: str) -> dict:
    return dict(table()[rule_id].get("params") or {})


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        if rule_id in _IMPL:
            raise RuntimeError(f"rule {rule_id} implemented twice")
        _IMPL[rule_id] = fn
        return fn
    return deco


def implemented() -> dict[str, RuleFn]:
    from tms.validate import load_all  # noqa: F401  (import side effect registers rules)
    load_all()
    return dict(_IMPL)


def run_rules(artifact: str, doc: Any, ctx: Context) -> list[Finding]:
    """Yielded items: message | (location, message) | (location, message, severity-override)."""
    out: list[Finding] = []
    impl = implemented()
    for rid, meta in table().items():
        if meta["artifact"] != artifact or rid not in impl:
            continue
        sev_default = meta["severity"]
        try:
            for item in impl[rid](doc, ctx, params(rid)) or ():
                if isinstance(item, str):
                    out.append(Finding(rid, sev_default, item))
                elif len(item) == 2:
                    out.append(Finding(rid, sev_default, item[1], item[0]))
                else:
                    out.append(Finding(rid, item[2], item[1], item[0]))
        except Exception as e:  # a crashing rule is itself an error, never a silent pass
            out.append(Finding(rid, "error", f"rule crashed: {type(e).__name__}: {e}"))
    return out
