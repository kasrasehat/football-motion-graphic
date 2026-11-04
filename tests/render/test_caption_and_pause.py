"""Caption placement and the pause treatment: both depend on real voice timing, so they only show up in the final render."""
from __future__ import annotations

import pytest

from tms.props.builder import _freeze_spans
from tms.render import projection
from tms.render.stage import CAPTION_BOX_TOP, caption_place

pytestmark = pytest.mark.fast

H = 1080
PROPS = {"height": H, "pitchVisible": [[0, 100]]}
CAP = {"from": 10, "to": 40}


def _ball_at(monkeypatch, y_of_frame):
    monkeypatch.setattr(projection, "project_ball", lambda _props, frame, _scale=1.0: (960.0, y_of_frame(frame)))


def test_a_ball_low_in_frame_but_above_the_caption_box_keeps_the_caption_at_the_bottom(monkeypatch):
    _ball_at(monkeypatch, lambda _f: H * CAPTION_BOX_TOP - 20)  # the AEK v Real Madrid S09 case: moving it hid the run
    assert caption_place(PROPS, CAP) == "bottom"


def test_a_ball_entering_the_caption_box_at_any_point_moves_the_caption_to_the_top(monkeypatch):
    _ball_at(monkeypatch, lambda f: H * CAPTION_BOX_TOP + 5 if f >= 34 else 300.0)  # not at the caption's midpoint
    assert caption_place(PROPS, CAP) == "top"


def test_a_caption_with_no_pitch_on_screen_stays_at_the_bottom(monkeypatch):
    _ball_at(monkeypatch, lambda _f: float(H))
    assert caption_place({"height": H, "pitchVisible": [[200, 300]]}, CAP) == "bottom"


def test_a_projection_failure_never_fails_the_render(monkeypatch):
    def boom(*_a, **_k):
        raise ValueError("no track")
    monkeypatch.setattr(projection, "project_ball", boom)
    assert caption_place(PROPS, CAP) == "bottom"


def _scene(*warp):
    return {"from": 100, "warp": [list(p) for p in warp]}


def test_a_pause_of_a_second_on_the_pitch_gets_the_paused_treatment():
    assert _freeze_spans(_scene((0, 0), (1, 30), (1, 60), (2, 90)), "pitch") == [[130, 160]]


def test_a_shorter_beat_on_the_pitch_does_not():
    assert _freeze_spans(_scene((0, 0), (1, 30), (1, 59), (2, 89)), "pitch") == []


def test_a_hold_on_a_graphic_card_does_not():
    assert _freeze_spans(_scene((0, 0), (1, 30), (1, 90), (2, 120)), "graphic") == []
