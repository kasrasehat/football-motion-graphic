"""Every rule in config/rules.yaml is implemented exactly once and has a negative test."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tms.validate.registry import implemented, table

pytestmark = pytest.mark.fast
TESTS = Path(__file__).resolve().parents[1]


def test_rule_ids_well_formed():
    for rid, meta in table().items():
        assert re.fullmatch(r"[A-Z]{2}-\d{2}", rid), rid
        assert meta["severity"] in ("error", "warning"), rid
        assert meta["text"], rid


def test_every_rule_implemented_and_no_orphans():
    impl = set(implemented())
    declared = set(table())
    assert declared - impl == set(), f"declared but not implemented: {sorted(declared - impl)}"
    assert impl - declared == set(), f"implemented but not declared: {sorted(impl - declared)}"


def test_every_rule_has_a_negative_test():
    text = "\n".join(p.read_text(encoding="utf-8") for p in TESTS.rglob("test_rules_*.py"))
    missing = [rid for rid in table() if f'"{rid}"' not in text]
    assert not missing, f"rules without a negative test in tests/**/test_rules_*.py: {missing}"
