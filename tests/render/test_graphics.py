"""M10: real Remotion stills of the match-preview data graphics (slow; `-m render`).

For every template fixture in tests/fixtures/graphics/ (Real Madrid v Arsenal, 90 frames, one graphic covering all
frames, pitch hidden) a still is rendered at a late frame (every reveal done, before the fade-out) at scale 0.5:
(a) the PNG has the expected size and is not blank (pixel variance, colour count)
(b) both team fills appear in it (CIEDE2000 < 12 against theme.teams.H/A.fill)
(c) a portrait variant renders too, and a still rendered twice is byte-identical
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import numpy as np
import pytest

from tests.helpers import FIX
from tms import remotion, theme
from tms.validate.colour import delta_e2000, hex_to_rgb

pytestmark = [
    pytest.mark.render,
    pytest.mark.skipif(not (shutil.which("node") and shutil.which("ffmpeg")), reason="needs node and ffmpeg on PATH"),
]

GRAPHICS = FIX / "graphics"
TEMPLATES = ("stat_compare", "form_guide", "h2h_strip", "lineup_board", "team_news", "key_player_duel",
             "probability_bar", "scoreline_grid", "prediction_card", "pattern_compare")
# every template draws team colours (header lock-up, swatches, bars, tokens, chips)
TEAM_COLOUR_TEMPLATES = TEMPLATES
LATE_FRAME = 75
SCALE = 0.5
MAX_DE = 12.0
MIN_TEAM_PIXELS = 40


def _props(template: str) -> dict:
    return json.loads((GRAPHICS / f"{template}.json").read_text(encoding="utf-8"))


def _rgb(png: Path, width: int, height: int) -> np.ndarray:
    """Decode a PNG to an (h, w, 3) uint8 array with ffmpeg."""
    p = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(png), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True)
    assert len(p.stdout) == width * height * 3, f"{png.name}: unexpected size ({len(p.stdout)} bytes)"
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(height, width, 3)


def _pixels_near(img: np.ndarray, hex_colour: str, max_de: float = MAX_DE) -> int:
    """Number of pixels within CIEDE2000 `max_de` of `hex_colour` (RGB prefilter, then exact dE on unique colours)."""
    target = np.array([round(c * 255) for c in hex_to_rgb(hex_colour)], dtype=np.int32)
    flat = img.reshape(-1, 3).astype(np.int32)
    cand = flat[np.sqrt(((flat - target) ** 2).sum(axis=1)) < 120]
    if not len(cand):
        return 0
    packed = (cand[:, 0] << 16) | (cand[:, 1] << 8) | cand[:, 2]
    uniq, counts = np.unique(packed, return_counts=True)
    return int(sum(int(n) for u, n in zip(uniq, counts) if delta_e2000(f"#{int(u):06x}", hex_colour) < max_de))


@pytest.fixture(scope="module")
def stills(tmp_path_factory):
    """Late-frame half-scale still per template, rendered lazily and cached for the module."""
    d = tmp_path_factory.mktemp("graphics")
    cache: dict[str, Path] = {}

    def get(name: str, props: dict | None = None, template: str | None = None) -> Path:
        if name not in cache:
            props_file = d / f"{name}.json"
            props_file.write_text(json.dumps(props if props is not None else _props(template or name)), encoding="utf-8")
            out = d / f"{name}.png"
            res = remotion.render("TacticVideo", out, props_file, still=LATE_FRAME, scale=SCALE, timeout=600)
            assert res.get("done") is True
            cache[name] = out
        return cache[name]

    return get


def test_every_template_has_a_valid_fixture():
    from tms.validate import validate_doc
    from tms.validate.registry import Context

    assert sorted(p.stem for p in GRAPHICS.glob("*.json")) == sorted(TEMPLATES)
    for t in TEMPLATES:
        doc = _props(t)
        errs = [f for f in validate_doc("render_props", doc, Context()) if f.severity == "error"]
        assert not errs, (t, [(f.rule, f.location, f.message) for f in errs])
        assert doc["pitchVisible"] == []
        (g,) = doc["graphics"]
        assert (g["template"], g["from"], g["to"]) == (t, 0, doc["durationInFrames"])
        assert g["reveals"] and max(r["frame"] for r in g["reveals"]) < LATE_FRAME - 20, "late frame must show everything"


@pytest.mark.parametrize("template", TEMPLATES)
def test_still_is_not_blank(stills, template):
    props = _props(template)
    w, h = int(props["width"] * SCALE), int(props["height"] * SCALE)
    img = _rgb(stills(template), w, h)
    luma = img.astype(np.float64) @ np.array([0.2126, 0.7152, 0.0722])
    assert luma.std() > 8.0, f"{template}: still looks blank (luma std {luma.std():.2f})"
    packed = (img[..., 0].astype(np.int32) << 16) | (img[..., 1].astype(np.int32) << 8) | img[..., 2]
    assert len(np.unique(packed)) > 200, f"{template}: too few colours for a data card"


@pytest.mark.parametrize("template", TEAM_COLOUR_TEMPLATES)
def test_team_fills_appear(stills, template):
    props = _props(template)
    w, h = int(props["width"] * SCALE), int(props["height"] * SCALE)
    img = _rgb(stills(template), w, h)
    for side in ("H", "A"):
        fill = props["theme"]["teams"][side]["fill"]
        n = _pixels_near(img, fill)
        assert n >= MIN_TEAM_PIXELS, f"{template}: {side} fill {fill} found on only {n} pixels (dE2000 < {MAX_DE})"


def test_portrait_variant_renders(stills):
    props = _props("lineup_board")
    props.update(orientation="portrait", width=1080, height=1920)
    img = _rgb(stills("lineup_board_portrait", props), 540, 960)
    assert img.reshape(-1, 3).std(axis=0).max() > 8.0
    assert _pixels_near(img, props["theme"]["teams"]["A"]["fill"]) >= MIN_TEAM_PIXELS


def test_same_still_twice_is_byte_identical(stills):
    a = stills("probability_bar")
    b = stills("probability_bar_again", _props("probability_bar"))
    assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()


CREST_FILL = "#e000c8"  # a generated shape, not a real club logo; magenta, which no fixture kit uses


def _crest_theme(root: Path) -> dict:
    """Theme with crests from a small SVG and PNG, through the same call the build makes."""
    (root / "h.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8" fill="{CREST_FILL}"/></svg>', encoding="utf-8")
    r, g, b = bytes.fromhex(CREST_FILL[1:])
    raw = zlib.compress(b"".join(b"\0" + bytes([r, g, b]) * 8 for _ in range(8)))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    (root / "a.png").write_bytes(theme.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    teams = {side: {**team, "crest": rel} for (side, team), rel in zip(_props("stat_compare")["theme"]["teams"].items(), ("h.svg", "a.png"))}
    return theme.render_theme({"show_crests": True, "teams": teams}, project_dir=root)["teams"]


@pytest.mark.parametrize("name,edit", [
    ("shell", lambda p: None),
    ("title_card", lambda p: p["graphics"][0].update(template="title_card", data={"headline": "Home v Away", "sub": "Preview"}, reveals=[])),
])
def test_crests_draw_and_stay_byte_identical(stills, tmp_path, name, edit):
    props = _props("stat_compare")
    edit(props)
    plain = _rgb(stills(f"crest_{name}_off", copy.deepcopy(props)), 960, 540)
    props["theme"]["teams"] = _crest_theme(tmp_path)
    a, b = stills(f"crest_{name}_on", props), stills(f"crest_{name}_on_again", props)
    assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()
    assert _pixels_near(plain, CREST_FILL) < MIN_TEAM_PIXELS <= _pixels_near(_rgb(a, 960, 540), CREST_FILL)


def test_crest_of_each_kind_validates_against_the_props_schema(tmp_path):
    from tms.validate import validate_doc
    from tms.validate.registry import Context

    props = _props("stat_compare")
    props["theme"]["teams"] = _crest_theme(tmp_path)
    assert not [f for f in validate_doc("render_props", props, Context()) if f.severity == "error"]
