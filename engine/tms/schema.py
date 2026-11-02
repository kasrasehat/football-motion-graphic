"""JSON Schema loading (Draft 2020-12) with cross-file $ref resolution."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tms import jsonio, paths

BASE = "https://tms.local/schemas/"


@lru_cache(maxsize=1)
def registry() -> Registry:
    resources = []
    for f in sorted(paths.schemas_dir().rglob("*.schema.json")):
        doc = jsonio.read_json(f)
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def artifact_schema_names() -> list[str]:
    return sorted(p.name.removesuffix(".schema.json") for p in (paths.schemas_dir() / "artifacts").glob("*.schema.json"))


@lru_cache(maxsize=None)
def validator_for(uri: str) -> Draft202012Validator:
    schema = registry().contents(uri)
    return Draft202012Validator(schema, registry=registry())


def artifact_validator(name: str) -> Draft202012Validator:
    return validator_for(f"{BASE}artifacts/{name}.schema.json")


def state_validator(defname: str) -> Draft202012Validator:
    schema = {"$ref": f"{BASE}state/state.schema.json#/$defs/{defname}"}
    return Draft202012Validator(schema, registry=registry())


def errors(validator: Draft202012Validator, doc: Any, limit: int = 25) -> list[str]:
    out = []
    for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{loc}: {e.message[:300]}")
        if len(out) >= limit:
            out.append("... (more errors truncated)")
            break
    return out


def validate_artifact(name: str, doc: Any) -> list[str]:
    return errors(artifact_validator(name), doc)
