"""BR rules: the fixture is clean; each mutation triggers exactly the intended rule."""
from __future__ import annotations

import pytest

from tms.validate.registry import Context
from tests.helpers import expect_clean, expect_violation, fixture

pytestmark = pytest.mark.fast


def test_fixtures_clean():
    expect_clean("brief", fixture("brief"))
    expect_clean("brief", fixture("brief.match"))


def test_BR01_duration_outside_mode_range():
    d = fixture("brief")
    d["target_duration_s"] = 200  # tactic max is 120
    expect_violation("BR-01", "brief", d)


def test_BR02_similar_fills():
    d = fixture("brief")
    d["teams"]["A"]["fill"] = "#c4122f"
    expect_violation("BR-02", "brief", d)


def test_BR03_low_contrast_number():
    d = fixture("brief")
    d["teams"]["H"]["text"] = "#d01530"
    expect_violation("BR-03", "brief", d)


def test_BR04_same_short_code():
    d = fixture("brief")
    d["teams"]["A"]["short"] = "RED"
    expect_violation("BR-04", "brief", d)


def test_BR05_user_source_without_text():
    d = fixture("brief")
    d["tactic"]["tactic_text"] = "short"
    expect_violation("BR-05", "brief", d)


def test_BR05_ai_source_without_topic():
    d = fixture("brief")
    d["tactic"].update(source="ai", tactic_text=None, topic=None)
    expect_violation("BR-05", "brief", d)


def test_BR06_kickoff_far_from_resolution():
    d = fixture("brief.match")
    d["match"]["kickoff_utc"] = "2026-12-30T20:00:00Z"
    expect_violation("BR-06", "brief", d)


def test_BR06_same_team():
    d = fixture("brief.match")
    d["match"]["away"] = "real madrid"
    expect_violation("BR-06", "brief", d)


def test_BR07_music_file_missing(tmp_path):
    d = fixture("brief")
    d["music"] = {"source": "file", "mood": "", "file": "media/nope.mp3"}
    expect_violation("BR-07", "brief", d, Context(project_dir=tmp_path / "fx-ifb-442"))


def test_BR08_budget_too_small():
    d = fixture("brief")
    d["budget"]["tts_chars_max"] = 100
    expect_violation("BR-08", "brief", d)


def test_BR09_api_without_fixture_id():
    d = fixture("brief.match")
    d["match"]["fixture_id"] = None
    expect_violation("BR-09", "brief", d)


def test_BR09_web_needs_two_sources():
    d = fixture("brief.match")
    d["match"]["resolution"] = {"method": "web", "resolved_at": "2026-11-02T12:00:00Z", "sources": ["https://a.test/x"]}
    expect_violation("BR-09", "brief", d)


def test_BR10_project_id_mismatch(tmp_path):
    d = fixture("brief")
    expect_violation("BR-10", "brief", d, Context(project_dir=tmp_path / "other-project"))


def test_BR11_mode_mismatch():
    expect_violation("BR-11", "brief", fixture("brief.match"), Context(mode="tactic"))
