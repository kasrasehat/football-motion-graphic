"""Real Remotion renders of the dense expected-shapes still (slow; `-m render`).

The geometry is proven in render/test/player-labels.test.ts; these look at actual pixels. Nothing may be drawn over a
token's fill, the ball or a ring on the dense fixture, and a still rendered twice is byte-identical.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.render.gen_still_fixtures import ASPECTS, dense_props
from tms import remotion
from tms.render import projection as P
from tms.validate.colour import delta_e2000

pytestmark = [
    pytest.mark.render,
    pytest.mark.skipif(not (shutil.which("node") and shutil.which("ffmpeg")), reason="needs node and ffmpeg on PATH"),
]

MAX_DE = 14.0


def _rgb(png: Path, width: int, height: int) -> np.ndarray:
    p = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(png), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True)
    assert len(p.stdout) == width * height * 3
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(height, width, 3)


def _hex(img: np.ndarray, x: float, y: float) -> str:
    r, g, b = img[int(y), int(x)]
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _render(props: dict, out: Path) -> Path:
    pf = out.with_suffix(".json")
    pf.write_text(json.dumps(props), encoding="utf-8")
    remotion.render("TacticVideo", out, props=pf, still=0, timeout=600)
    return out


@pytest.fixture(scope="module")
def renders(tmp_path_factory) -> dict[str, tuple[dict, np.ndarray, Path]]:
    d = tmp_path_factory.mktemp("still")
    out = {}
    for name in ASPECTS:
        props = dense_props(name)
        png = _render(props, d / f"{name}.png")
        out[name] = (props, _rgb(png, props["width"], props["height"]), png)
    return out


@pytest.mark.parametrize("name", tuple(ASPECTS))
def test_no_token_fill_is_covered(renders, name):
    props, img, _png = renders[name]
    w, h, o = props["width"], props["height"], props["orientation"]
    r = P.token_radius_px(P.camera_at(props, 0)[2], w, h, o)
    bad = []
    for e in props["entities"]:
        x, y = P.project_player(props, e["id"], 0)
        fill = props["theme"]["teams"][e["team"]]["fill"]
        # above and below the shirt number, left and right of it: pure fill unless something sits on the token
        for dx, dy in ((0, -0.72), (0, 0.72), (-0.8, 0), (0.8, 0)):
            got = _hex(img, x + dx * r, y + dy * r)
            if delta_e2000(got, fill) > MAX_DE:
                bad.append((e["id"], e["number"], dx, dy, got))
    assert not bad, bad


@pytest.mark.parametrize("name", tuple(ASPECTS))
def test_ball_is_visible(renders, name):
    props, img, _png = renders[name]
    x, y = P.project_ball(props, 0)
    assert delta_e2000(_hex(img, x, y), "#f4f6f8") < MAX_DE


def test_rings_are_uncovered_at_16x9(renders):
    props, img, _png = renders["landscape"]
    w, h, o = props["width"], props["height"], props["orientation"]
    cam = P.camera_at(props, 0)
    u = P.resolution_factor(w, h)
    ring_r = P.ring_outer_radius_px(P.token_radius_px(cam[2], w, h, o), u) - 3.5 * u
    accent = props["theme"]["accent"]
    bad = []
    for wx, wy in next(o for o in props["overlays"] if o["kind"] == "ring")["geom"]["static"]:
        x, y = P.world_to_screen(wx, wy, cam, w, h, o)
        for i in range(12):
            a = i * math.pi / 6
            got = _hex(img, x + ring_r * math.cos(a), y + ring_r * math.sin(a))
            if delta_e2000(got, accent) > MAX_DE:
                bad.append((wx, wy, i, got))
    assert not bad, bad


def test_panel_is_drawn(renders):
    props, img, _png = renders["landscape"]
    x0, y0, x1, y1 = props["principleRail"]["rect"]
    # a spot along the bottom of the panel, under the last principle: the panel colour, not grass
    assert delta_e2000(_hex(img, (x0 + x1) / 2, y1 - 14), props["theme"]["panel"]) < MAX_DE


def test_still_is_byte_identical_twice(renders, tmp_path):
    props, _img, png = renders["landscape"]
    again = _render(props, tmp_path / "again.png")
    assert hashlib.sha256(png.read_bytes()).hexdigest() == hashlib.sha256(again.read_bytes()).hexdigest()
