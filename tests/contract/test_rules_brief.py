"""BR rules: the fixture is clean; each mutation triggers exactly the intended rule."""
from __future__ import annotations

import pytest

from tms import theme
from tms.validate.registry import Context
from tests.helpers import expect_clean, expect_violation, findings, fixture

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


PNG = theme.PNG_SIGNATURE + b"\0\0\0\rIHDR" + bytes(17) + b"\0\0\0\1IDAT" + bytes(5) + b"\0\0\0\0IEND" + bytes(4)
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4"/></svg>'


def crest_project(tmp_path, h=("media/h.png", PNG), a=("media/a.svg", SVG)):
    """A brief with show_crests on and its project folder; each crest is (path in the brief, file bytes)."""
    root = tmp_path / "fx-ifb-442"
    d = fixture("brief")
    d["show_crests"] = True
    for side, (rel, raw) in (("H", h), ("A", a)):
        d["teams"][side]["crest"] = rel
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(raw)
    return d, Context(project_dir=root)


def test_BR12_clean_with_a_png_and_an_svg(tmp_path):
    d, c = crest_project(tmp_path)
    assert "BR-12" not in {f.rule for f in findings("brief", d, c)}


def test_BR12_off_by_default_nothing_is_checked():
    assert fixture("brief").get("show_crests") is None
    d = fixture("brief")
    d["teams"]["H"]["crest"] = "../not/looked/at.png"
    expect_clean("brief", d)


def test_BR12_crest_missing_from_the_brief(tmp_path):
    d, c = crest_project(tmp_path)
    del d["teams"]["A"]["crest"]
    expect_violation("BR-12", "brief", d, c)


def test_BR12_file_missing(tmp_path):
    d, c = crest_project(tmp_path)
    d["teams"]["H"]["crest"] = "media/nope.png"
    expect_violation("BR-12", "brief", d, c)


def test_BR12_needs_a_project_folder():
    d = fixture("brief")
    d["show_crests"] = True
    expect_violation("BR-12", "brief", d)


@pytest.mark.parametrize("rel,raw", [
    ("media/h.jpg", b"\xff\xd8\xff\xe0"),
    ("media/h.png", b"\xff\xd8\xff\xe0"),  # a JPEG named .png
    ("media/h.svg", PNG),
    ("media/h.svg", b"<html></html>"),
    ("media/h.png", theme.PNG_SIGNATURE),  # truncated
    ("media/h.png", theme.PNG_SIGNATURE + b"\0\0\0\rIHDR" + bytes(17) + b"\0\0\0\x08acTL" + bytes(12) + b"\0\0\0\1IDAT" + bytes(5)),  # animated
    ("media/h.svg", b'<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'),
    ("media/h.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://x.test/c.png"/></svg>'),
    ("media/h.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://x.test/f#a)"/></svg>'),
    ("media/h.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://x.test/a.css";</style></svg>'),
    ("media/h.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'),
    ("media/h.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect><animate attributeName="x"/></rect></svg>'),
    ("media/h.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect style="animation: spin 1s"/></svg>'),
])
def test_BR12_not_a_still_self_contained_png_or_svg(tmp_path, rel, raw):
    d, c = crest_project(tmp_path, h=(rel, raw))
    expect_violation("BR-12", "brief", d, c)


def test_BR12_size_limit_is_inclusive(tmp_path):
    d, c = crest_project(tmp_path, h=("media/h.png", PNG + bytes(theme.CREST_MAX_BYTES - len(PNG))))
    assert "BR-12" not in {f.rule for f in findings("brief", d, c)}
    d, c = crest_project(tmp_path, h=("media/h.png", PNG + bytes(theme.CREST_MAX_BYTES - len(PNG) + 1)))
    expect_violation("BR-12", "brief", d, c)


@pytest.mark.parametrize("rel", ["../outside.png", "media/../../outside.png", "..\\outside.png"])
def test_BR12_path_climbs_out_of_the_project(tmp_path, rel):
    d, c = crest_project(tmp_path)
    (tmp_path / "outside.png").write_bytes(PNG)
    d["teams"]["H"]["crest"] = rel
    expect_violation("BR-12", "brief", d, c)


def test_BR12_absolute_path_even_inside_the_project(tmp_path):
    d, c = crest_project(tmp_path)
    d["teams"]["H"]["crest"] = str(c.project_dir / "media" / "h.png")
    expect_violation("BR-12", "brief", d, c)
    d["teams"]["H"]["crest"] = "C:/crests/h.png"
    expect_violation("BR-12", "brief", d, c)


def test_BR12_symlink_cannot_lead_out_of_the_project(tmp_path):
    d, c = crest_project(tmp_path)
    (tmp_path / "outside.png").write_bytes(PNG)
    link = c.project_dir / "media" / "link.png"
    try:
        link.symlink_to(tmp_path / "outside.png")
    except OSError:
        pytest.skip("this account cannot create symlinks")
    d["teams"]["H"]["crest"] = "media/link.png"
    expect_violation("BR-12", "brief", d, c)


def test_theme_has_no_crest_unless_asked_for_even_when_the_brief_names_one(tmp_path):
    d, c = crest_project(tmp_path)
    d["show_crests"] = False
    t = theme.render_theme(d, project_dir=c.project_dir)
    assert all("crest" not in team for team in t["teams"].values())
    del d["show_crests"]
    assert theme.render_theme(d) == t  # no project folder needed, nothing read


def test_theme_embeds_crests_as_data_uris_only(tmp_path):
    d, c = crest_project(tmp_path)
    teams = theme.render_theme(d, project_dir=c.project_dir)["teams"]
    assert teams["H"]["crest"].startswith("data:image/png;base64,") and teams["A"]["crest"].startswith("data:image/svg+xml;base64,")
    assert "media/" not in teams["H"]["crest"]


def test_theme_refuses_a_bad_crest_rather_than_dropping_it(tmp_path):
    d, c = crest_project(tmp_path)
    with pytest.raises(ValueError, match="project folder"):
        theme.render_theme(d)
    (c.project_dir / "media" / "h.png").unlink()
    with pytest.raises(ValueError, match="not found"):
        theme.render_theme(d, project_dir=c.project_dir)
