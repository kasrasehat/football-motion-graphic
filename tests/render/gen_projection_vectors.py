"""Regenerates tests/fixtures/projection_vectors.json (shared by vitest and pytest).

Run:  .venv/Scripts/python.exe tests/render/gen_projection_vectors.py

Expected values are computed here with an INDEPENDENT formulation (homogeneous 3x3 matrices composed as
translate(-cam) -> rotate(theta) -> scale(s) -> translate(viewport centre)), not with tms.render.projection,
so the vectors cross-check both implementations instead of restating one of them.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "projection_vectors.json"


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def translate(tx, ty):
    return [[1, 0, tx], [0, 1, ty], [0, 0, 1]]


def scale(s):
    return [[s, 0, 0], [0, s, 0], [0, 0, 1]]


def rotate(theta):
    # Screen coordinates are y-down; theta = -90 deg sends world +x (attack direction) to screen up.
    c, s = round(math.cos(theta), 15), round(math.sin(theta), 15)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def project(world, cam, width, height, orientation):
    cx, cy, w = cam
    if orientation == "portrait":
        theta, along_x_px = -math.pi / 2, height  # pitch x runs along the screen's vertical axis
    else:
        theta, along_x_px = 0.0, width
    s = along_x_px / w
    m = mat_mul(translate(width / 2, height / 2), mat_mul(scale(s), mat_mul(rotate(theta), translate(-cx, -cy))))
    x, y = world
    return [m[0][0] * x + m[0][1] * y + m[0][2], m[1][0] * x + m[1][1] * y + m[1][2]], s


def radius(s, width, height):
    return max(1.0 * s, 13.0 * min(width, height) / 1080)


FULL = [52.5, 34.0, 105.0]
SIZES = {"landscape": [(1920, 1080), (960, 540)], "portrait": [(1080, 1920), (540, 960)], "square": [(1080, 1080)]}

CASES = [
    # (name, orientation, size, camera, world)
    ("landscape centre", "landscape", (1920, 1080), FULL, [52.5, 34.0]),
    ("landscape corner top-left", "landscape", (1920, 1080), FULL, [0.0, 0.0]),
    ("landscape corner bottom-right", "landscape", (1920, 1080), FULL, [105.0, 68.0]),
    ("landscape corner top-right", "landscape", (1920, 1080), FULL, [105.0, 0.0]),
    ("landscape home goal centre", "landscape", (1920, 1080), FULL, [0.0, 34.0]),
    ("landscape penalty spot right", "landscape", (1920, 1080), FULL, [94.0, 34.0]),
    ("landscape zoomed w60 at H2 pivot", "landscape", (1920, 1080), [40.0, 40.0, 60.0], [40.0, 39.0]),
    ("landscape zoomed w60 off-centre", "landscape", (1920, 1080), [40.0, 40.0, 60.0], [25.1, 45.79]),
    ("landscape zoomed w30 tight", "landscape", (1920, 1080), [80.0, 20.0, 30.0], [88.5, 13.84]),
    ("landscape wide w125 fit", "landscape", (1920, 1080), [52.5, 34.0, 125.0], [0.0, 68.0]),
    ("landscape half-res centre", "landscape", (960, 540), FULL, [52.5, 34.0]),
    ("landscape half-res corner", "landscape", (960, 540), [40.0, 40.0, 60.0], [0.0, 0.0]),
    ("portrait centre", "portrait", (1080, 1920), FULL, [52.5, 34.0]),
    ("portrait home goal is bottom", "portrait", (1080, 1920), FULL, [0.0, 34.0]),
    ("portrait away goal is top", "portrait", (1080, 1920), FULL, [105.0, 34.0]),
    ("portrait corner top-left", "portrait", (1080, 1920), FULL, [0.0, 0.0]),
    ("portrait corner bottom-right", "portrait", (1080, 1920), FULL, [105.0, 68.0]),
    ("portrait right flank is screen right", "portrait", (1080, 1920), FULL, [52.5, 68.0]),
    ("portrait zoomed w60", "portrait", (1080, 1920), [40.0, 40.0, 60.0], [40.0, 28.0]),
    ("portrait half-res zoomed", "portrait", (540, 960), [70.0, 30.0, 45.0], [61.0, 40.0]),
    ("portrait full-height fit w118", "portrait", (1080, 1920), [52.5, 34.0, 118.0], [105.0, 0.0]),
    ("square centre", "square", (1080, 1080), FULL, [52.5, 34.0]),
    ("square corner top-left", "square", (1080, 1080), FULL, [0.0, 0.0]),
    ("square corner bottom-right", "square", (1080, 1080), FULL, [105.0, 68.0]),
    ("square zoomed w50", "square", (1080, 1080), [30.0, 50.0, 50.0], [36.0, 61.0]),
    ("square tiny-token floor", "square", (1080, 1080), [52.5, 34.0, 140.0], [11.0, 34.0]),
    ("landscape tiny-token floor", "landscape", (1920, 1080), [52.5, 34.0, 160.0], [52.5, 0.0]),
]


def main() -> None:
    vectors = []
    for name, orient, (width, height), cam, world in CASES:
        screen, s = project(world, cam, width, height, orient)
        vectors.append({
            "name": name, "orientation": orient, "width": width, "height": height,
            "camera_m": cam, "world_m": world,
            "screen_px": [round(screen[0], 9), round(screen[1], 9)],
            "px_per_m": round(s, 9),
            "token_radius_px": round(radius(s, width, height), 9),
        })
    doc = {
        "description": "Shared world(m)->screen(px) projection vectors for render/src/lib/projection.ts and "
                       "engine/tms/render/projection.py. Regenerate with tests/render/gen_projection_vectors.py.",
        "tolerance_px": 1e-6,
        "vectors": vectors,
    }
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(vectors)} vectors to {OUT}")


if __name__ == "__main__":
    main()
