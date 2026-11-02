"""Harness mirrors: in sync, valid for both Claude Code and Codex, and every quoted command exists."""
from __future__ import annotations

import re
import tomllib

import pytest
import yaml

from tms import cli, manifest, paths
from tms.harness import sync

pytestmark = pytest.mark.fast
ROOT = paths.root()

# Stage skills / agents written by later milestones. This set may only SHRINK (M-gates assert it).
PENDING_SKILLS: set[str] = set()
PENDING_AGENTS: set[str] = set()


def _front(path):
    return sync.parse_front(path.read_text(encoding="utf-8"), str(path)).meta


def test_mirrors_up_to_date():
    assert sync.sync(check=True) == [], "run `.venv/Scripts/tms sync-harness`"


def test_codex_skills_frontmatter_is_valid():
    """Mirrors the constraints of Codex's skill validator (name regex, description length, allowed keys)."""
    skills = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
    assert skills
    for f in skills:
        meta = _front(f)
        assert set(meta) <= {"name", "description", "license", "allowed-tools", "metadata"}, f
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"]) and len(meta["name"]) <= 64
        assert meta["name"] == f.parent.name
        assert len(meta["description"]) <= 1024 and "<" not in meta["description"] and ">" not in meta["description"]


def test_claude_skills_frontmatter():
    for f in sorted((ROOT / ".claude/skills").glob("*/SKILL.md")):
        meta = _front(f)
        assert set(meta) <= {"name", "description", "disable-model-invocation", "allowed-tools"}, f


def test_user_only_skills_are_not_implicit_in_either_harness():
    for sdir in (ROOT / "skills").glob("*/"):
        meta = _front(sdir / "SKILL.md")
        if (meta.get("harness") or {}).get("user_only"):
            assert _front(ROOT / ".claude/skills" / sdir.name / "SKILL.md")["disable-model-invocation"] is True
            oy = yaml.safe_load((ROOT / ".agents/skills" / sdir.name / "agents/openai.yaml").read_text(encoding="utf-8"))
            assert oy["policy"]["allow_implicit_invocation"] is False


def test_codex_agents_parse_with_required_fields():
    files = sorted((ROOT / ".codex/agents").glob("*.toml"))
    assert files
    for f in files:
        d = tomllib.loads(f.read_text(encoding="utf-8"))
        assert d["name"] == f.stem and d["description"] and d["developer_instructions"].strip()
        assert d["model_reasoning_effort"] in ("low", "medium", "high")


def test_claude_agents_frontmatter():
    for f in sorted((ROOT / ".claude/agents").glob("*.md")):
        meta = _front(f)
        assert meta["name"] == f.stem and meta["description"] and meta["tools"]


def test_agents_md_size_budget():
    assert (ROOT / "AGENTS.md").stat().st_size < 24 * 1024


def test_claude_md_imports_agents_md():
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0].strip() == "@AGENTS.md"


def _subcommands() -> dict:
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    return sub.choices


def test_every_quoted_tms_command_exists():
    """Skills, agents and AGENTS.md may only quote real CLI subcommands."""
    choices = _subcommands()
    files = list((ROOT / "skills").rglob("*.md")) + list((ROOT / "agents").glob("*.md")) + [ROOT / "AGENTS.md"]
    bad = []
    for f in files:
        for m in re.finditer(r"\.venv/Scripts/tms\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?", f.read_text(encoding="utf-8")):
            cmd, sub = m.group(1), m.group(2)
            if cmd not in choices:
                bad.append(f"{f.name}: {cmd}")
                continue
            nested = [a for a in choices[cmd]._actions if getattr(a, "choices", None) and isinstance(a.choices, dict)]
            if nested and sub and sub not in nested[0].choices and not sub.startswith("-"):
                # positional arg that is not a nested subcommand (e.g. `stage begin`) is fine if the parser takes choices
                pos = [a for a in choices[cmd]._actions if a.dest not in ("help",) and not a.option_strings]
                if not any(getattr(a, "choices", None) and sub in a.choices for a in pos):
                    bad.append(f"{f.name}: {cmd} {sub}")
    assert not bad, bad


def test_stage_skills_exist_or_are_pending():
    for s in manifest.load()["stages"]:
        name = manifest.stage(s)["skill"].split("/")[1]
        exists = (ROOT / "skills" / name / "SKILL.md").is_file()
        assert exists or name in PENDING_SKILLS, f"stage {s}: missing skill {name}"
        assert not (exists and name in PENDING_SKILLS), f"{name} exists: remove it from PENDING_SKILLS"


def test_reviewer_agents_exist_or_are_pending():
    for s in manifest.load()["stages"]:
        for q in manifest.stage(s)["qa"]:
            exists = (ROOT / "agents" / f"{q['agent']}.md").is_file()
            assert exists or q["agent"] in PENDING_AGENTS, f"reviewer {q['agent']} missing"
            assert not (exists and q["agent"] in PENDING_AGENTS), f"{q['agent']} exists: remove it from PENDING_AGENTS"


def test_project_context_generated_block_lists_all_stages():
    text = (ROOT / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
    for s in manifest.load()["stages"]:
        assert f"`{s}`" in text
