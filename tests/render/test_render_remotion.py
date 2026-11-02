"""M3: real Remotion renders of the render_props fixture (slow; `-m render`).

(a) the fixture renders at scale 0.5 to 90 frames, 960x540, 30/1
(b) a portrait variant (1080x1920) renders 90 frames
(c) pixel probes: tokens H4, A9, H9 and the ball sit where the Python projection says, in their colours
(d) the same still rendered twice is byte-identical
(e) invalid props fail fast with the readable calculateMetadata error
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import FIX
from tms import paths, remotion
from tms.render import projection as P
from tms.validate.colour import delta_e2000

pytestmark = [
    pytest.mark.render,
    pytest.mark.skipif(not (shutil.which("node") and shutil.which("ffmpeg") and shutil.which("ffprobe")),
                       reason="needs node, ffmpeg and ffprobe on PATH"),
]

PROPS_FILE = FIX / "artifacts" / "render_props.json"
PROBE_FRAME = 10
PROBE_TOKENS = ("H4", "A9", "H9")
MAX_DE = 12.0


def _props() -> dict:
    return json.loads(PROPS_FILE.read_text(encoding="utf-8"))


def _write(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _ffprobe(path: Path) -> dict:
    p = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames,width,height,r_frame_rate,codec_name,pix_fmt",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)["streams"][0]


def _pixel(png: Path, x: float, y: float) -> str:
    """sRGB hex of the pixel containing screen point (x, y), sampled with ffmpeg."""
    xi, yi = int(x), int(y)
    p = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(png), "-vf", f"crop=1:1:{xi}:{yi},format=rgb24",
                        "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True)
    assert len(p.stdout) == 3, p.stderr
    return "#" + p.stdout.hex()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def stills(tmp_path_factory) -> dict[str, Path]:
    """Frame-10 stills of the fixture (rendered twice) and of a portrait variant."""
    d = tmp_path_factory.mktemp("stills")
    por = _props()
    por.update(orientation="portrait", width=1080, height=1920)
    por_file = _write(d / "portrait.json", por)
    out = {}
    for name, props in (("land_a", PROPS_FILE), ("land_b", PROPS_FILE), ("portrait", por_file)):
        res = remotion.render("TacticVideo", d / f"{name}.png", props, still=PROBE_FRAME, timeout=600)
        assert res.get("done") is True
        out[name] = d / f"{name}.png"
    return out


def test_fixture_renders_90_frames_at_half_scale(tmp_path):
    out = tmp_path / "fixture.mp4"
    remotion.render("TacticVideo", out, PROPS_FILE, scale=0.5, timeout=900)
    s = _ffprobe(out)
    assert int(s["nb_read_frames"]) == 90
    assert (s["width"], s["height"]) == (960, 540)
    assert s["r_frame_rate"] == "30/1"
    assert s["codec_name"] == "h264"


def test_portrait_variant_renders_90_frames(tmp_path):
    por = _props()
    por.update(orientation="portrait", width=1080, height=1920)
    out = tmp_path / "portrait.mp4"
    remotion.render("TacticVideo", out, _write(tmp_path / "portrait.json", por), scale=0.5, timeout=900)
    s = _ffprobe(out)
    assert int(s["nb_read_frames"]) == 90
    assert (s["width"], s["height"]) == (540, 960)  # 1080x1920 composition at scale 0.5
    assert s["r_frame_rate"] == "30/1"


def _probe_points(cx: float, cy: float, r: float, ball: tuple[float, float]) -> list[tuple[float, float]]:
    """Points on the token disc, 0.6 r from the projected centre (the exact centre carries the white shirt number;
    0.6 r is outside the glyph and inside the ring), in the four screen directions, minus any within r of the ball
    (the ball and its shadow are drawn over the token when the player has it at his feet)."""
    pts = [(cx, cy - 0.6 * r), (cx - 0.6 * r, cy), (cx, cy + 0.6 * r), (cx + 0.6 * r, cy)]
    return [(x, y) for x, y in pts if ((x - ball[0]) ** 2 + (y - ball[1]) ** 2) ** 0.5 > r]


@pytest.mark.parametrize("variant", ["land_a", "portrait"])
@pytest.mark.parametrize("pid", PROBE_TOKENS)
def test_token_pixels_match_team_fill(stills, variant, pid):
    props = _props()
    if variant == "portrait":
        props.update(orientation="portrait", width=1080, height=1920)
    team = pid[0]
    fill = props["theme"]["teams"][team]["fill"]
    cx, cy = P.project_player(props, pid, PROBE_FRAME)
    r = P.token_radius_px(P.camera_at(props, PROBE_FRAME)[2], props["width"], props["height"], props["orientation"])
    pts = _probe_points(cx, cy, r, P.project_ball(props, PROBE_FRAME))
    assert len(pts) >= 2
    for x, y in pts:
        got = _pixel(stills[variant], x, y)
        de = delta_e2000(got, fill)
        assert de < MAX_DE, f"{pid} @({x:.1f},{y:.1f}) in {variant}: got {got}, want ~{fill} (dE2000 {de:.1f})"
    # and the token is local: 2.2 r above the centre is no longer the team fill
    outside = _pixel(stills[variant], cx, cy - 2.2 * r)
    assert delta_e2000(outside, fill) > MAX_DE, f"{pid}: team colour leaks outside the token ({outside})"


@pytest.mark.parametrize("variant", ["land_a", "portrait"])
def test_ball_pixel_is_white(stills, variant):
    props = _props()
    if variant == "portrait":
        props.update(orientation="portrait", width=1080, height=1920)
    bx, by = P.project_ball(props, PROBE_FRAME)
    got = _pixel(stills[variant], bx, by)
    assert delta_e2000(got, "#ffffff") < MAX_DE, f"ball pixel {got} is not white-ish"


def test_same_still_twice_is_byte_identical(stills):
    assert _sha(stills["land_a"]) == _sha(stills["land_b"])


def test_invalid_props_fail_with_readable_error(tmp_path):
    bad = _props()
    bad["fps"] = 25
    bad["theme"]["accent"] = "#12345"
    with pytest.raises(RuntimeError) as e:
        remotion.render("TacticVideo", tmp_path / "bad.png", _write(tmp_path / "bad.json", bad), still=0, timeout=600)
    msg = str(e.value)
    assert "Invalid render_props" in msg and "/fps" in msg and "/theme/accent" in msg


def test_default_props_fixture_copy_is_identical():
    """The composition's defaultProps file mirrors the test fixture (vitest checks deep equality too)."""
    src = paths.render_dir() / "src" / "fixtures" / "render_props.fixture.json"
    assert json.loads(src.read_text(encoding="utf-8")) == _props()
