"""Virtual camera: per-frame rect (cx, cy, w) in metres, w = visible extent along pitch x.
Visible extent along pitch y = w * yfrac (9/16 for 16:9 and 9:16 because portrait rotates the pitch; 1 for 1:1)."""
from __future__ import annotations

import math

from tms.choreo import motion as M
from tms.choreo.compile import SceneResult, eval_time
from tms.choreo.motion import DT, FPS
from tms.tactic.geometry import LENGTH, WIDTH

MARGIN = 6.0
MIN_W = 32.0
ZOOM_RATE = 0.5   # max |d ln w / dt| per second we aim for (CH-51 allows 0.6)
PAN_RATE = 0.38   # max pan speed as a fraction of w per second (CH-51 allows 0.45)


def yfrac(aspect: str) -> float:
    return 1.0 if aspect == "1:1" else 9 / 16


def w_fit(aspect: str) -> float:
    return max(LENGTH, WIDTH / yfrac(aspect)) * 1.04


def clamp_rect(cx: float, cy: float, w: float, aspect: str) -> tuple[float, float, float]:
    w = min(max(w, MIN_W), w_fit(aspect))
    hw, hh = w / 2, w * yfrac(aspect) / 2
    lo_x, hi_x = hw - MARGIN, LENGTH + MARGIN - hw
    lo_y, hi_y = hh - MARGIN, WIDTH + MARGIN - hh
    cx = LENGTH / 2 if lo_x > hi_x else min(max(cx, lo_x), hi_x)
    cy = WIDTH / 2 if lo_y > hi_y else min(max(cy, lo_y), hi_y)
    return cx, cy, w


def full(aspect: str) -> tuple[float, float, float]:
    return LENGTH / 2, WIDTH / 2, w_fit(aspect)


def _pos(res: SceneResult, target: str, f: int) -> tuple[float, float]:
    f = min(f, res.n)
    if target == "ball":
        b = res.ball[f]
        return b[0], b[1]
    return res.players[target][f]


def fit_rect(points: list[tuple[float, float]], pad: float, aspect: str) -> tuple[float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    bw, bh = max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
    w = max(bw, bh / yfrac(aspect), MIN_W)
    return clamp_rect((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, w, aspect)


def _static_target(res, k, tk, n, aspect, f):
    if k["mode"] == "full":
        return full(aspect)
    if k["mode"] == "rect":
        return clamp_rect(*k["rect"], aspect)
    if k["mode"] == "frame":
        fa = int(round(tk * FPS))
        fb = min(int(round((tk + k.get("dur_s", 1.0) + 1.0) * FPS)), n)
        return fit_rect([_pos(res, tg, ff) for tg in k["targets"] for ff in range(fa, max(fb, fa + 1), 3)],
                        k.get("pad_m", 8.0), aspect)
    p = _pos(res, k["target"], f)
    return clamp_rect(p[0], p[1], k["w_m"], aspect)


def scene_camera(res: SceneResult, aspect: str, prev_rect, hard_cut: bool) -> tuple[list[tuple[float, float, float]], list[dict]]:
    """Per-frame rects for frames 0..n-1 of the scene, plus the resolved keys."""
    n = res.n
    keys = []
    for k in res.plan.get("camera", []):
        t = eval_time(k["at"], res.times, n * DT)
        if t is None:
            continue
        keys.append((t, k))
    keys.sort(key=lambda z: z[0])
    out = []
    cur = prev_rect if (prev_rect is not None and not hard_cut) else None
    spring = None
    ki = -1
    trans_from, trans_t0, trans_dur = None, 0.0, 0.0
    resolved = []
    for f in range(n):
        t = f * DT
        while ki + 1 < len(keys) and keys[ki + 1][0] <= t + 1e-9:
            ki += 1
            tk, k = keys[ki]
            resolved.append({"tau": round(tk, 4), "mode": k["mode"]})
            trans_from = cur
            trans_t0, trans_dur = tk, k.get("dur_s", 1.0 if cur is not None else 0.0)
            if k["mode"] == "follow":
                spring = None
            if cur is not None and trans_dur > 0:
                # stretch the move so zoom/pan stay within CH-51 (easeInOutCubic peaks at 3x the mean rate)
                goal = _static_target(res, k, keys[ki][0], n, aspect, f)
                if goal is not None:
                    dlog = abs(math.log(goal[2] / cur[2]))
                    dpan = math.hypot(goal[0] - cur[0], goal[1] - cur[1])
                    trans_dur = max(trans_dur, 3.0 * dlog / ZOOM_RATE, 3.0 * dpan / (PAN_RATE * min(goal[2], cur[2])))
        if ki < 0:
            target = cur or full(aspect)
        else:
            k = keys[ki][1]
            if k["mode"] == "full":
                target = full(aspect)
            elif k["mode"] == "rect":
                target = clamp_rect(*k["rect"], aspect)
            elif k["mode"] == "frame":
                fa = int(round(keys[ki][0] * FPS))
                fb = min(int(round((keys[ki][0] + k.get("dur_s", 1.0) + 1.0) * FPS)), n)
                pts = [_pos(res, tg, ff) for tg in k["targets"] for ff in range(fa, max(fb, fa + 1), 3)]
                target = fit_rect(pts, k.get("pad_m", 8.0), aspect)
            else:  # follow (critically damped spring on the target point)
                p = _pos(res, k["target"], f)
                if spring is None:
                    spring = [p[0], p[1], 0.0, 0.0]
                omega = 3.0
                for i in (0, 1):
                    x, v = spring[i], spring[i + 2]
                    a = omega * omega * (p[i] - x) - 2 * omega * v
                    v += a * DT
                    spring[i + 2] = v
                    spring[i] = x + v * DT
                target = clamp_rect(spring[0], spring[1], k["w_m"], aspect)
        if trans_from is not None and trans_dur > 0 and t - trans_t0 < trans_dur:
            e = M.ease_in_out_cubic((t - trans_t0) / trans_dur)
            # zoom in log space keeps perceived zoom speed constant
            w = math.exp(math.log(trans_from[2]) + (math.log(target[2]) - math.log(trans_from[2])) * e)
            rect = clamp_rect(trans_from[0] + (target[0] - trans_from[0]) * e,
                              trans_from[1] + (target[1] - trans_from[1]) * e, w, aspect)
        else:
            rect = target
        out.append(rect)
        cur = rect
    return out, resolved
