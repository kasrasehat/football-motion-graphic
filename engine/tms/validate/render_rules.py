"""RP (render_props) and FQ (render_report) rules."""
from __future__ import annotations

import json
import math

from tms import jsonio, manifest
from tms.validate.registry import rule

ASPECT = {"16:9": "landscape", "9:16": "portrait", "1:1": "square"}


@rule("RP-01")
def array_lengths(doc, ctx, p):
    n = doc["durationInFrames"]
    for pid, arr in doc["tracks"]["players"].items():
        if len(arr) != 2 * n:
            yield f"tracks/players/{pid}", f"{len(arr)} values, expected {2 * n}"
    if len(doc["tracks"]["ball"]) != 3 * n:
        yield "tracks/ball", f"{len(doc['tracks']['ball'])} values, expected {3 * n}"
    if len(doc["camera"]) != 3 * n:
        yield "camera", f"{len(doc['camera'])} values, expected {3 * n}"


@rule("RP-02")
def resolution(doc, ctx, p):
    brief = ctx.other("brief")
    if brief and ASPECT[brief["aspect"]] != doc["orientation"]:
        yield "orientation", f"{doc['orientation']} but the brief asks for {brief['aspect']}"
    w, h = doc["width"], doc["height"]
    want = {"landscape": w > h, "portrait": h > w, "square": w == h}[doc["orientation"]]
    if not want:
        yield "width", f"{w}x{h} does not match orientation {doc['orientation']}"


@rule("RP-03")
def windows_in_range(doc, ctx, p):
    n = doc["durationInFrames"]
    for kind in ("overlays", "captions", "scenes", "graphics"):
        for item in doc[kind]:
            if not 0 <= item["from"] < item["to"] <= n:
                yield f"{kind}/{item.get('id', item['from'])}", f"window {item['from']}-{item['to']} outside 0-{n}"


@rule("RP-04")
def inputs_current(doc, ctx, p):
    if ctx.project_dir is None:
        return
    for name, h in doc["inputs"].items():
        if name not in manifest.artifact_names():
            continue
        f = manifest.artifact_path(ctx.project_dir, name)
        if f.is_file() and jsonio.sha256_file(f) != h:
            yield f"inputs/{name}", f"{name} changed after these props were built — rebuild them"


@rule("RP-05")
def props_size(doc, ctx, p):
    mb = len(json.dumps(doc, separators=(",", ":"))) / 1e6
    if mb > p["max_mb"]:
        yield "(root)", f"{mb:.1f} MB of props"


@rule("RP-06")
def onscreen_speed(doc, ctx, p):
    n = doc["durationInFrames"]
    frozen = set()
    for a, b in doc["freeze"]:
        frozen |= set(range(a - 4, b + 5))
    cuts = set()
    for s in doc["scenes"]:
        cuts |= set(range(s["from"] - 3, s["from"] + 4))
    visible = set()
    for a, b in doc["pitchVisible"]:
        visible |= set(range(a, b))
    for pid, arr in doc["tracks"]["players"].items():
        for f in range(3, n - 3):
            if f in frozen or f in cuts or f not in visible:
                continue
            dx = (arr[2 * (f + 3)] - arr[2 * (f - 3)]) / 100
            dy = (arr[2 * (f + 3) + 1] - arr[2 * (f - 3) + 1]) / 100
            v = math.hypot(dx, dy) / (6 / 30)
            if v > p["vmax"]:
                yield pid, f"{pid} appears to move {v:.1f} m/s at frame {f}"
                break


def _fq(rid):
    def fn(doc, ctx, p):
        for c in doc["checks"]:
            if c["rule"] == rid and not c["ok"]:
                yield rid, c["detail"]
        if not any(c["rule"] == rid for c in doc["checks"]):
            yield rid, "check missing from render_report"
    return fn


for _rid in ("FQ-01", "FQ-02", "FQ-03", "FQ-04", "FQ-05", "FQ-06", "FQ-07", "FQ-08"):
    rule(_rid)(_fq(_rid))
