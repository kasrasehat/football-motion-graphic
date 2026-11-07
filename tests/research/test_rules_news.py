"""News, rumour and expert facts: registered keys, and WC-05's limits on how a rumour may be sourced."""
from __future__ import annotations

import copy

import pytest

from tests.helpers import fixture
from tests.research.test_rules_research import ctx, expect_violation
from tms import validate as V
from tms.research import facts as FX

pytestmark = pytest.mark.fast

SRC = {"kind": "web", "url": "https://www.marca.com/x", "title": "t", "publisher": "Marca", "tier": 1, "quote": "q", "retrieved_at": "2026-11-02T12:00:00Z"}


def web(key="H.rumour.dressing_room", value="Marca reports a dispute.", confidence="medium", source=SRC):
    d = copy.deepcopy(fixture("web_claims"))
    d["claims"].append({"id": "W-900", "fact_key": key, "category": "news", "statement": "A reported story.", "value": value, "unit": None,
                        "as_of": "2026-11-02T10:00:00Z", "confidence": confidence, "sources": [dict(source)]})
    return d


@pytest.mark.parametrize("key", ["H.news.coach", "A.rumour.transfer", "H.expert.shape", "fixture.expert.outcome"])
def test_the_new_keys_are_registered_and_take_a_sentence(key):
    assert FX.type_problem(key, "One plain sentence.") is None
    assert FX.type_problem(key, 3) is not None


def test_a_prefix_key_does_not_match_a_longer_word():
    assert FX.spec("fixture.experts") is None


def test_a_rumour_can_be_properly_sourced():
    found = V.validate_doc("web_claims", web(), ctx())
    assert not [f for f in found if f.rule == "WC-05"]


def test_a_rumour_is_never_high_confidence():
    expect_violation("WC-05", "web_claims", web(confidence="high"), ctx())


def test_a_rumour_needs_a_major_source():
    low = {**SRC, "url": "https://rumours.example/x", "publisher": "Blog", "tier": 3}
    expect_violation("WC-05", "web_claims", web(source=low), ctx())


def test_established_news_is_not_held_to_the_rumour_rule():
    low = {**SRC, "url": "https://club.example/x", "publisher": "Club", "tier": 3}
    found = V.validate_doc("web_claims", web(key="H.news.coach", confidence="high", source=low), ctx())
    assert not [f for f in found if f.rule == "WC-05"]
