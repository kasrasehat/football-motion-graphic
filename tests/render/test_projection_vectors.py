"""M3: the Python projection (tms.render.projection) agrees with the shared vectors used by the TS renderer."""
from __future__ import annotations

import json

import pytest

from tests.helpers import FIX
from tms.render import projection as P

pytestmark = pytest.mark.fast

DOC = json.loads((FIX / "projection_vectors.json").read_text(encoding="utf-8"))
VECTORS = DOC["vectors"]
TOL = DOC["tolerance_px"]


def test_vector_file_shape():
    assert len(VECTORS) >= 20
    assert TOL <= 1e-6
    assert {v["orientation"] for v in VECTORS} == {"landscape", "portrait", "square"}


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_projection_matches_vectors(v):
    sx, sy = P.world_to_screen(*v["world_m"], v["camera_m"], v["width"], v["height"], v["orientation"])
    assert abs(sx - v["screen_px"][0]) <= TOL
    assert abs(sy - v["screen_px"][1]) <= TOL
    assert abs(P.px_per_metre(v["camera_m"][2], v["width"], v["height"], v["orientation"]) - v["px_per_m"]) <= TOL
    assert abs(P.token_radius_px(v["camera_m"][2], v["width"], v["height"], v["orientation"]) - v["token_radius_px"]) <= TOL
    wx, wy = P.screen_to_world(sx, sy, v["camera_m"], v["width"], v["height"], v["orientation"])
    assert abs(wx - v["world_m"][0]) < 1e-9 and abs(wy - v["world_m"][1]) < 1e-9


def test_portrait_home_attacks_up():
    cam = (52.5, 34.0, 105.0)
    home_goal = P.world_to_screen(0, 34, cam, 1080, 1920, "portrait")
    away_goal = P.world_to_screen(105, 34, cam, 1080, 1920, "portrait")
    assert home_goal[1] > away_goal[1]
    assert P.world_to_screen(52.5, 60, cam, 1080, 1920, "portrait")[0] > 540  # home's right flank is screen right


def test_props_helpers_read_centimetre_tracks():
    props = json.loads((FIX / "artifacts" / "render_props.json").read_text(encoding="utf-8"))
    assert P.camera_at(props, 0) == (52.5, 34.0, 125.7)
    assert P.camera_at(props, 10_000) == P.camera_at(props, props["durationInFrames"] - 1)  # clamped
    x, y = P.player_at(props, "H4", 10)
    assert (round(x * 100), round(y * 100)) == tuple(props["tracks"]["players"]["H4"][20:22])
    sx, sy = P.project_player(props, "H4", 10, scale=0.5)
    fx, fy = P.project_player(props, "H4", 10)
    assert (sx, sy) == pytest.approx((fx / 2, fy / 2))
