"""pipeline.yaml integrity: graph per mode, artifacts registry, gates, locked stage order."""
from __future__ import annotations

import pytest

from tms import manifest, paths, schema

pytestmark = pytest.mark.fast


def test_manifest_validates_against_its_schema():
    manifest.load.cache_clear()
    assert manifest.load()["version"] == "1"


def test_locked_stage_order():
    assert manifest.mode_stages("tactic") == ["intake", "tactic", "storyboard", "audio", "render", "package"]
    assert manifest.mode_stages("match_preview") == ["intake", "research", "analysis", "storyboard", "audio", "render", "package"]


@pytest.mark.parametrize("mode", ["tactic", "match_preview"])
def test_every_input_is_produced_upstream(mode):
    produced: set[str] = set()
    for s in manifest.mode_stages(mode):
        missing = [i for i in manifest.stage_inputs(s, mode) if i not in produced]
        assert not missing, f"{mode}/{s} consumes {missing} not produced by an earlier stage"
        produced |= set(manifest.stage_produces(s))


@pytest.mark.parametrize("mode", ["tactic", "match_preview"])
def test_each_artifact_has_one_producer_per_mode(mode):
    seen: dict[str, str] = {}
    for s in manifest.mode_stages(mode):
        for a in manifest.stage_produces(s):
            assert a not in seen, f"{a} produced by both {seen[a]} and {s} in {mode}"
            seen[a] = s


def test_every_artifact_has_registry_entry_and_schema():
    names = set(schema.artifact_schema_names())
    for s in manifest.load()["stages"]:
        for a in manifest.stage_produces(s):
            assert a in manifest.artifact_names(), f"{s} produces unregistered artifact {a}"
    for a in manifest.artifact_names():
        assert manifest.artifact(a).schema in names, f"artifact {a} has no schema"


@pytest.mark.parametrize("mode", ["tactic", "match_preview"])
def test_approval_words_unique_per_mode(mode):
    words = [manifest.approval_word(s) for s in manifest.mode_stages(mode) if manifest.gate(s) == "human"]
    assert len(words) == len(set(words))
    assert all(words)


def test_only_package_is_optional_and_last():
    for mode in manifest.modes():
        st = manifest.mode_stages(mode)
        assert [s for s in st if manifest.is_optional(s)] == ["package"]
        assert st[-1] == "package"


def test_engine_artifacts_live_in_build_and_agent_artifacts_in_artifacts():
    for a in manifest.artifact_names():
        spec = manifest.artifact(a)
        assert (spec.writer, spec.dir) in {("agent", "artifacts"), ("engine", "build")}, a


def test_duration_ranges_sane():
    for mode in manifest.modes():
        lo, hi, d = manifest.duration_range(mode)
        assert lo < d < hi


def test_project_context_mentions_every_stage():
    """Doc drift guard (the reference repo's docs disagreed on stage counts)."""
    ctx = (paths.root() / "PROJECT_CONTEXT.md")
    if not ctx.is_file():
        pytest.skip("PROJECT_CONTEXT.md is written in M2")
    text = ctx.read_text(encoding="utf-8")
    for s in manifest.load()["stages"]:
        assert f"`{s}`" in text, f"PROJECT_CONTEXT.md does not mention stage {s}"
