"""Master timeline (integer frames @ 30 fps / 48 kHz): warps, captions, provisional (animatic) timelines."""
from __future__ import annotations

import re

FPS = 30
SR = 48000
SPF = SR // FPS  # samples per frame
INTRO_FRAMES = 54   # 1.8 s title card
OUTRO_FRAMES = 75   # 2.5 s end card
WPS_EST = 2.6       # estimated words per second (matches NS-03)

CAPTION = {"max_line": 42, "max_lines": 2, "max_cps": 20.0, "min_frames": 24, "max_frames": 180}


def tau_at(warp: list[list[float]], offset: float) -> float:
    """Invert a piecewise-linear warp: output frame offset (within the scene) -> scene-local tau seconds."""
    if offset <= warp[0][1]:
        return warp[0][0]
    for (t0, f0), (t1, f1) in zip(warp, warp[1:]):
        if f0 <= offset <= f1:
            if f1 == f0:
                return t0
            return t0 + (t1 - t0) * (offset - f0) / (f1 - f0)
    return warp[-1][0]


def frame_of_tau(warp: list[list[float]], tau: float) -> float:
    """Forward warp: scene-local tau -> output frame offset (holds map to their first frame)."""
    if tau <= warp[0][0]:
        return warp[0][1]
    for (t0, f0), (t1, f1) in zip(warp, warp[1:]):
        if t0 <= tau <= t1 and t1 > t0:
            return f0 + (f1 - f0) * (tau - t0) / (t1 - t0)
    return warp[-1][1]


# ------------------------------------------------------------------ captions
def wrap(words: list[str], width: int) -> list[list[int]]:
    """Greedy wrap; when the result is two lines, rebalance them to similar lengths (subtitle convention)."""
    lines, cur, n = [], [], 0
    for i, w in enumerate(words):
        add = len(w) + (1 if cur else 0)
        if cur and n + add > width:
            lines.append(cur)
            cur, n = [], 0
            add = len(w)
        cur.append(i)
        n += add
    if cur:
        lines.append(cur)
    if len(lines) == 2:
        best = None
        for c in range(1, len(words)):
            l1, l2 = len(" ".join(words[:c])), len(" ".join(words[c:]))
            if l1 <= width and l2 <= width:
                cost = abs(l1 - l2) + (8 if words[c - 1].lower().strip(",") in ("a", "an", "the", "of", "to") else 0)
                if best is None or cost < best[0]:
                    best = (cost, c)
        if best:
            c = best[1]
            lines = [list(range(c)), list(range(c, len(words)))]
    return lines


def _fits(words: list[dict]) -> bool:
    disp = [w["display"] for w in words]
    dur = (words[-1]["to"] - words[0]["from"]) / FPS
    chars = len(" ".join(disp))
    return (len(wrap(disp, CAPTION["max_line"])) <= CAPTION["max_lines"] and dur * FPS <= CAPTION["max_frames"]
            and (dur <= 0 or chars / max(dur, 0.5) <= CAPTION["max_cps"] or len(words) < 3))


WEAK_END = {"a", "an", "the", "of", "to", "in", "on", "at", "for", "with", "and", "or", "but", "from", "into", "by",
            "between", "next", "his", "their", "its", "is", "are", "who", "that"}
GOOD_START = {"and", "but", "so", "then", "while", "when", "because", "which", "where", "before", "after"}


def _split_sentence(ws: list[dict]) -> list[list[dict]]:
    """Split a sentence into chunks that fit: best single cut by a readability cost, recursively."""
    if _fits(ws) or len(ws) < 4:
        return [ws]
    best, best_cost = None, None
    for c in range(2, len(ws) - 1):
        left, right = ws[:c], ws[c:]
        cl = len(" ".join(w["display"] for w in left))
        cr = len(" ".join(w["display"] for w in right))
        last = left[-1]["display"].lower().strip(",;:")
        cost = abs(cl - cr)
        if left[-1]["display"].endswith((",", ";", ":")):
            cost -= 18
        if right[0]["display"].lower() in GOOD_START:
            cost -= 10
        if last in WEAK_END:
            cost += 25
        if best_cost is None or cost < best_cost:
            best, best_cost = c, cost
    return _split_sentence(ws[:best]) + _split_sentence(ws[best:])


def chunk_captions(words: list[dict]) -> list[dict]:
    """words: [{i, display, from, to}] in order (one clip). One or more chunks per sentence; per-word line index."""
    sentences, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w["display"]):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    caps = []
    for sent in sentences:
        for part in _split_sentence(sent):
            disp = [w["display"] for w in part]
            lines = wrap(disp, CAPTION["max_line"])
            line_of = {k: li for li, idxs in enumerate(lines) for k in idxs}
            a = part[0]["from"]
            caps.append({"from": a, "to": max(part[-1]["to"], a + CAPTION["min_frames"]),
                         "lines": [" ".join(disp[k] for k in idxs) for idxs in lines],
                         "words": [{"t": w["display"], "from": w["from"], "to": w["to"], "line": line_of[j]} for j, w in enumerate(part)],
                         "word_index": [part[0]["i"], part[-1]["i"]]})
    for k in range(len(caps) - 1):  # never overlap the next chunk
        caps[k]["to"] = min(caps[k]["to"], caps[k + 1]["from"])
    return caps


# ------------------------------------------------------------------ provisional timeline (animatic)
def provisional(choreo: dict, narration: dict, project_id: str) -> dict:
    """Silent animatic timeline: motion at 1x, freeze holds stretched to fit the estimated narration,
    captions from evenly spaced estimated word timings. The real timeline comes from the voice-over (audio stage)."""
    lines = {ln["scene"]: ln for ln in narration["lines"]}
    scenes, words_out, caps_out = [], [], []
    f = INTRO_FRAMES
    wi = 0
    for s in choreo["scenes"]:
        n = int(round(s["len"] * FPS))
        ln = lines.get(s["id"])
        text = "" if (ln is None or ln["silent"]) else ln["text"]
        toks = text.split()
        est = len(toks) / WPS_EST + 0.4
        extra = max(0.0, est - s["len"])
        warp = [[0.0, 0]]
        for h in sorted(s["holds"], key=lambda h: h["tau"]):
            if extra <= 0:
                break
            add = min(h["max_s"], extra)
            tl = h["tau"] - s["tau0"]
            fo = int(round(tl * FPS)) + (warp[-1][1] - int(round(warp[-1][0] * FPS)))
            warp += [[round(tl, 4), fo], [round(tl, 4), fo + int(round(add * FPS))]]
            extra -= add
        shift = warp[-1][1] - int(round(warp[-1][0] * FPS))
        warp.append([round(s["len"], 4), n + shift])
        length = n + shift
        scenes.append({"id": s["id"], "from": f, "to": f + length, "vo": None, "warp": warp})
        clip_words = []
        t = f + 6
        per = FPS / WPS_EST
        for k, w in enumerate(toks):
            a, b = int(round(t)), int(round(t + per * 0.9))
            clip_words.append({"i": wi, "clip": s["id"], "display": w, "from": a, "to": max(b, a + 1)})
            wi += 1
            t += per + (FPS * 0.25 if re.search(r"[.!?]$", w) else 0)
        words_out += clip_words
        for c in chunk_captions(clip_words):
            c["to"] = min(c["to"], f + length)
            caps_out.append(c)
        f += length
    total = f + OUTRO_FRAMES
    return {
        "version": "1", "project_id": project_id, "inputs": {}, "fps": FPS, "sr": SR, "frames": total,
        "intro": {"from": 0, "to": INTRO_FRAMES}, "outro": {"from": f, "to": total},
        "scenes": scenes, "vo": [], "words": words_out, "anchors": [],
        "captions": [{"id": f"C{k + 1:02d}", "from": c["from"], "to": max(c["to"], c["from"] + 1), "lines": c["lines"],
                      "words": c["word_index"], "place": "bottom"} for k, c in enumerate(caps_out)],
        "duck": {"windows": [], "depth_db": -10, "attack_ms": 150, "release_ms": 450},
    }
