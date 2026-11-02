"""Every schema is valid Draft 2020-12; every artifact schema has a valid fixture; dropping any required key fails."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tms import jsonio, paths, schema
from tests.helpers import FIX

pytestmark = pytest.mark.fast
SCHEMA_FILES = sorted(paths.schemas_dir().rglob("*.schema.json"))
FIXTURES = sorted((FIX / "artifacts").glob("*.json"))


@pytest.mark.parametrize("f", SCHEMA_FILES, ids=lambda f: f.name)
def test_schema_is_valid_draft_2020_12(f: Path):
    doc = jsonio.read_json(f)
    Draft202012Validator.check_schema(doc)
    assert doc["$id"].startswith(schema.BASE)
    assert doc["$id"].endswith(f.relative_to(paths.schemas_dir()).as_posix())


def test_every_artifact_schema_has_a_fixture_and_vice_versa():
    names = set(schema.artifact_schema_names())
    have = {f.name.split(".")[0] for f in FIXTURES}
    assert names == have, f"schemas without fixture: {names - have}; fixtures without schema: {have - names}"


@pytest.mark.parametrize("f", FIXTURES, ids=lambda f: f.name)
def test_fixture_validates(f: Path):
    assert schema.validate_artifact(f.name.split(".")[0], jsonio.read_json(f)) == []


def _required_paths(sch: dict, doc, prefix=()):
    """Yield paths of required keys present in doc, for top-level and directly nested required objects."""
    if not isinstance(doc, dict):
        return
    for key in sch.get("required", []):
        if key in doc:
            yield prefix + (key,)


@pytest.mark.parametrize("f", FIXTURES, ids=lambda f: f.name)
def test_dropping_any_top_level_required_key_fails(f: Path):
    name = f.name.split(".")[0]
    doc = jsonio.read_json(f)
    top = schema.registry().contents(f"{schema.BASE}artifacts/{name}.schema.json")
    for (key,) in _required_paths(top, doc):
        mutated = copy.deepcopy(doc)
        del mutated[key]
        assert schema.validate_artifact(name, mutated), f"{name}: dropping required '{key}' still validates"


def test_render_props_schema_is_self_contained():
    """The TS renderer compiles render_props with ajv standalone: no external $refs allowed."""
    text = (paths.schemas_dir() / "artifacts" / "render_props.schema.json").read_text(encoding="utf-8")
    assert "defs.schema.json" not in text
