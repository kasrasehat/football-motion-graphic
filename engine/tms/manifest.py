"""Access to pipeline.yaml — modes, stages, artifacts, QA requirements."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from tms import paths, schema


@lru_cache(maxsize=1)
def load() -> dict:
    doc = yaml.safe_load((paths.root() / "pipeline.yaml").read_text(encoding="utf-8"))
    errs = schema.errors(schema.validator_for(f"{schema.BASE}pipeline.schema.json"), doc)
    if errs:
        raise ValueError("pipeline.yaml invalid:\n" + "\n".join(errs))
    return doc


def modes() -> list[str]:
    return list(load()["modes"])


def mode_stages(mode: str) -> list[str]:
    return list(load()["modes"][mode]["stages"])


def duration_range(mode: str) -> tuple[int, int, int]:
    d = load()["modes"][mode]["duration_s"]
    return d["min"], d["max"], d["default"]


def stage(name: str) -> dict:
    return load()["stages"][name]


def stage_inputs(name: str, mode: str) -> list[str]:
    inp = stage(name)["inputs"]
    return list(inp.get(mode, [])) if isinstance(inp, dict) else list(inp)


def stage_produces(name: str) -> list[str]:
    return list(stage(name)["produces"])


def stage_qa(name: str, mode: str) -> list[dict]:
    return [q for q in stage(name)["qa"] if "modes" not in q or mode in q["modes"]]


def is_optional(name: str) -> bool:
    return bool(stage(name).get("optional", False))


def gate(name: str) -> str:
    return stage(name)["gate"]


def approval_word(name: str) -> str | None:
    return stage(name).get("approval_word")


def stage_for_word(mode: str, word: str) -> str | None:
    for s in mode_stages(mode):
        if approval_word(s) == word:
            return s
    return None


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    dir: str
    writer: str
    schema: str


def artifact(name: str) -> ArtifactSpec:
    a = load()["artifacts"][name]
    return ArtifactSpec(name, a["dir"], a["writer"], a["schema"])


def artifact_names() -> list[str]:
    return list(load()["artifacts"])


def artifact_path(project_dir: Path, name: str) -> Path:
    spec = artifact(name)
    return Path(project_dir) / spec.dir / f"{name}.json"


def artifact_for_path(path: Path) -> tuple[Path, str] | None:
    """Map projects/<slug>/(artifacts|build)/<name>.json -> (project_dir, artifact name)."""
    p = Path(path).resolve()
    if p.suffix != ".json" or p.parent.name not in ("artifacts", "build"):
        return None
    name = p.stem
    if name not in load()["artifacts"] or artifact(name).dir != p.parent.name:
        return None
    project_dir = p.parent.parent
    if not (project_dir / "project.json").is_file():
        return None
    return project_dir, name
