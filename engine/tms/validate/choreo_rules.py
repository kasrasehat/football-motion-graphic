"""CH — choreography rules. Re-check physics, possession, overlays and camera on the dense tracks."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from tms.validate.registry import rule

FPS = 30


class Tracks:
    def __init__(self, doc):
        n = doc["tracks"]["n"]
        self.n = n
        self.P = {pid: np.asarray(v, dtype=float).reshape(-1, 2)[:n] / 100.0 for pid, v in doc["tracks"]["players"].items()}
        self.B = np.asarray(doc["tracks"]["ball"], dtype=float).reshape(-1, 3)[:n] / 100.0
        cam = doc.get("camera_track") or []
        self.C = np.asarray(cam, dtype=float).reshape(-1, 3)[:n] / 100.0 if cam else None
        self.scene_of = np.zeros(n, dtype=int)
        self.kind = []
        self.cuts = set()   # frames where a reset/cut boundary happens (jumps allowed)
        self.bounds = []
        for i, s in enumerate(doc["scenes"]):
            a = int(round(s["tau0"] * FPS))
            b = min(a + int(round(s["len"] * FPS)), n)
            self.scene_of[a:b] = i
            self.kind.append(s["kind"])
            self.bounds.append((a, b))
            if s["transition"] in ("reset", "cut") or s["kind"] == "graphic" or (i > 0 and doc["scenes"][i - 1]["kind"] == "graphic"):
                self.cuts.add(a)
        self.pitch = np.array([self.kind[self.scene_of[f]] == "pitch" for f in range(n)], dtype=bool)

    def near_cut(self, f: int, w: int = 4) -> bool:
        return any(abs(f - c) <= w for c in self.cuts)


_cache: dict[int, Tracks] = {}


def T(doc) -> Tracks:
    key = id(doc)
    if key not in _cache:
        _cache.clear()
        _cache[key] = Tracks(doc)
    return _cache[key]


def _report(doc, rid):
    for e in doc["report"]["errors"]:
        if e.get("rule") == rid:
            yield e.get("scene") or "", e["message"]


def _velocity(p: np.ndarray, half: int) -> np.ndarray:
    v = np.zeros_like(p)
    if len(p) > 2 * half:
        v[half:-half] = (p[2 * half:] - p[:-2 * half]) / (2 * half / FPS)
    return v


def _gk_ids(ctx):
    spec = ctx.other("tactic_spec")
    if not spec:
        return {"H1", "A1"}
    return {p["id"] for t in "HA" for p in spec["teams"][t]["players"] if p["role"] == "GK"}


def _yfrac(doc):
    return 1.0 if doc.get("aspect") == "1:1" else 9 / 16


def _w_fit(doc):
    return max(105.0, 68.0 / _yfrac(doc)) * 1.04


# --------------------------------------------------------------------- structure
@rule("CH-01")
def scene_counts(doc, ctx, p):
    yield from _report(doc, "CH-01")
    n = len(doc["scenes"])
    if not p["min_scenes"] <= n <= p["max_scenes"]:
        yield "scenes", f"{n} scenes (allowed {p['min_scenes']}-{p['max_scenes']})"
    for s in doc["scenes"]:
        if s["kind"] == "pitch" and not p["min_s"] <= s["len"] <= p["max_s"] + 1e-6:
            yield s["id"], f"pitch scene lasts {s['len']:.1f} s (allowed {p['min_s']}-{p['max_s']})"


@rule("CH-02")
def refs_resolve(doc, ctx, p):
    yield from _report(doc, "CH-02")


@rule("CH-03")
def principles_covered(doc, ctx, p):
    plan, spec = ctx.other("scene_plan"), ctx.other("tactic_spec")
    if not plan or not spec:
        return
    pitch = [s for s in plan["scenes"] if s["kind"] == "pitch"]
    shown = {pid for s in pitch for pid in s.get("principles", [])}
    battles = {b for s in pitch for b in s.get("battles", [])}
    analysis = ctx.other("match_analysis") if ctx.mode == "match_preview" else None
    if analysis:
        for tb in analysis["tactical_battles"]:
            if tb["id"] not in battles:
                yield "scenes", f"tactical battle {tb['id']} ({tb['title']}) is never shown"
    else:
        for pr in spec["principles"]:
            if pr["id"] not in shown:
                yield "scenes", f"principle {pr['id']} ({pr['name']}) is never shown"
    known = {pr["id"] for pr in spec["principles"]}
    for s in pitch:
        bad = [x for x in s.get("principles", []) if x not in known]
        if bad:
            yield s["id"], f"cites unknown principles {bad}"
        if s["purpose"] in ("explain", "demonstrate", "exploit", "battle") and not (s.get("principles") or s.get("battles")):
            yield s["id"], f"{s['purpose']} scene cites no principle or battle"


@rule("CH-04")
def overrides_modest(doc, ctx, p):
    plan, spec = ctx.other("scene_plan"), ctx.other("tactic_spec")
    if not plan or not spec:
        return
    from tms.choreo.compile import snapshot_positions
    snap = snapshot_positions(spec)
    ov = plan["start"]["overrides"]
    if len(ov) > p["max_overrides"]:
        yield "start/overrides", f"{len(ov)} overrides (> {p['max_overrides']}): consider a different tactic snapshot"
    for pid, xy in ov.items():
        d = math.dist(snap[pid], xy)
        if d > p["max_shift_m"]:
            yield f"start/overrides/{pid}", f"{pid} starts {d:.1f} m from its snapshot position"


@rule("CH-05")
def scenes_change(doc, ctx, p):
    plan = ctx.other("scene_plan")
    if not plan:
        return
    for s in plan["scenes"]:
        if s["kind"] == "pitch" and not (s["actions"] or s["overlays"] or len(s["camera"]) > 1 or s["camera"][0]["mode"] != "full"):
            yield s["id"], "nothing changes in this scene"


# --------------------------------------------------------------------- players
def _physics_frames(t: Tracks, f: int) -> bool:
    return t.pitch[f] and not t.near_cut(f)


@rule("CH-10")
def speed_limits(doc, ctx, p):
    t = T(doc)
    gks = _gk_ids(ctx)
    half = max(1, int(round(p["window_s"] * FPS / 2)))
    for pid, pos in t.P.items():
        sp = np.linalg.norm(_velocity(pos, half), axis=1)
        lim = p["vmax_gk"] if pid in gks else p["vmax"]
        bad = [f for f in np.nonzero(sp > lim)[0] if _physics_frames(t, f)]
        if bad:
            f = bad[0]
            yield pid, f"{pid} moves at {sp[f]:.1f} m/s at tau={f / FPS:.2f}s (> {lim})"


@rule("CH-11")
def long_sprints(doc, ctx, p):
    t = T(doc)
    for pid, pos in t.P.items():
        sp = np.linalg.norm(_velocity(pos, 3), axis=1)
        run = 0
        for f in range(t.n):
            run = run + 1 if sp[f] > p["v"] and t.pitch[f] else 0
            if run > p["max_s"] * FPS:
                yield pid, f"{pid} sprints above {p['v']} m/s for more than {p['max_s']} s (tau {f / FPS:.1f}s)"
                break


@rule("CH-12")
def accel_limits(doc, ctx, p):
    t = T(doc)
    for pid, pos in t.P.items():
        v = _velocity(pos, 3)
        a = np.linalg.norm(_velocity(v, 4), axis=1)
        frames = [f for f in range(t.n) if _physics_frames(t, f) and not t.near_cut(f, 10)]
        if not frames:
            continue
        fa = max(frames, key=lambda f: a[f])
        if a[fa] > p["amax"]:
            yield pid, f"{pid} accelerates at {a[fa]:.1f} m/s^2 at tau={fa / FPS:.2f}s (> {p['amax']})"
        elif a[fa] > p["awarn"]:
            yield pid, f"{pid} accelerates at {a[fa]:.1f} m/s^2 at tau={fa / FPS:.2f}s", "warning"


@rule("CH-13")
def no_teleport(doc, ctx, p):
    t = T(doc)
    for pid, pos in t.P.items():
        step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        bad = [f + 1 for f in np.nonzero(step > p["max_step_m"])[0] if (f + 1) not in t.cuts and t.pitch[f + 1]]
        if bad:
            yield pid, f"{pid} jumps {step[bad[0] - 1]:.2f} m in one frame at tau={bad[0] / FPS:.2f}s"


@rule("CH-14")
def players_in_bounds(doc, ctx, p):
    t = T(doc)
    m = p["margin"]
    for pid, pos in t.P.items():
        out = np.nonzero((pos[:, 0] < -m) | (pos[:, 0] > 105 + m) | (pos[:, 1] < -m) | (pos[:, 1] > 68 + m))[0]
        if len(out):
            yield pid, f"{pid} leaves the pitch at tau={out[0] / FPS:.2f}s ({pos[out[0]].round(1).tolist()})"


def _contact_windows(doc, ctx):
    """Frames where specific opponent pairs may touch (duels, tackles, presses at the ball)."""
    win = []
    plan = ctx.other("scene_plan")
    starts = {s["id"]: s["tau0"] for s in doc["scenes"]}
    for a in doc["actions"]:
        if "@duel#" in a["handle"] or "@press#" in a["handle"] or "@mark#" in a["handle"]:
            pid = a["handle"].split(":")[1].split("@")[0]
            win.append((pid, None, a["tau0"], a["tau1"]))
    for e in doc["events"]:
        if e["type"] in ("tackle", "intercept"):
            win.append((e.get("by"), e.get("on"), e["tau0"] - 1.0, e["tau1"] + 0.5))
    del plan, starts
    return win


@rule("CH-15")
def collisions(doc, ctx, p):
    t = T(doc)
    ids = sorted(t.P)
    wins = _contact_windows(doc, ctx)

    def excused(a, b, f):
        tau = f / FPS
        return any((x in (a, b)) and (y is None or y in (a, b)) and lo <= tau <= hi for x, y, lo, hi in wins)
    reported = set()
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            d = np.linalg.norm(t.P[a] - t.P[b], axis=1)
            same = a[0] == b[0]
            lim = p["teammates_min"] if same else p["opponents_min"]
            bad = [f for f in np.nonzero(d < lim)[0] if t.pitch[f] and not (not same and excused(a, b, f))]
            if same:
                runs, run = [], 0
                for f in range(t.n):
                    run = run + 1 if f in set(bad) else 0
                    if run > 3:
                        runs.append(f)
                        break
                bad = runs
            if bad and (a, b) not in reported:
                reported.add((a, b))
                yield f"{a}/{b}", f"{a} and {b} collide ({d[bad[0]]:.2f} m) at tau={bad[0] / FPS:.2f}s"
            elif not same:
                close = (d < p["opponents_warn"]) & t.pitch
                run, worst = 0, 0
                for f in range(t.n):
                    run = run + 1 if close[f] and not excused(a, b, f) else 0
                    worst = max(worst, run)
                if worst > p["warn_s"] * FPS:
                    yield f"{a}/{b}", f"{a} and {b} overlap visually for {worst / FPS:.1f} s", "warning"


@rule("CH-16")
def dead_shape(doc, ctx, p):
    t = T(doc)
    gks = _gk_ids(ctx)
    flight = np.zeros(t.n, dtype=bool)
    for ps in doc["possession"]:
        if ps["state"] == "flight":
            flight[int(ps["tau0"] * FPS):int(ps["tau1"] * FPS)] = True
    out = [pid for pid in t.P if pid not in gks]
    sp = np.stack([np.linalg.norm(_velocity(t.P[pid], 3), axis=1) for pid in out])
    static_share = (sp < p["v"]).mean(axis=0)
    run = 0
    for f in range(t.n):
        run = run + 1 if flight[f] and static_share[f] >= p["share"] else 0
        if run > p["s"] * FPS:
            yield "tracks", f"almost everyone stands still while the ball moves (tau {f / FPS:.1f}s)"
            return


# --------------------------------------------------------------------- ball
@rule("CH-20")
def possession_contiguous(doc, ctx, p):
    segs = sorted(doc["possession"], key=lambda s: (s["tau0"], s["tau1"]))
    total = doc["tracks"]["n"] / FPS
    cur = 0.0
    for s in segs:
        if s["tau1"] - s["tau0"] < 1e-9 and s["state"] in ("loose", "dead"):
            continue
        if s["tau0"] > cur + 1.5 / FPS:
            yield "possession", f"gap in possession between {cur:.2f}s and {s['tau0']:.2f}s"
        if s["tau0"] < cur - 1.5 / FPS:
            yield "possession", f"overlapping possession at {s['tau0']:.2f}s"
        cur = max(cur, s["tau1"])
    if cur < total - 1.5 / FPS:
        yield "possession", f"possession timeline ends at {cur:.2f}s, video at {total:.2f}s"


@rule("CH-21")
def ball_with_carrier(doc, ctx, p):
    t = T(doc)
    for s in doc["possession"]:
        if s["state"] != "held" or s["by"] not in t.P:
            continue
        fa, fb = int(round(s["tau0"] * FPS)), min(int(round(s["tau1"] * FPS)), t.n)
        if fb <= fa:
            continue
        d = np.linalg.norm(t.B[fa:fb, :2] - t.P[s["by"]][fa:fb], axis=1)
        if d.max() > p["max_m"]:
            f = fa + int(d.argmax())
            yield s["by"], f"ball {d.max():.2f} m from its carrier {s['by']} at tau={f / FPS:.2f}s"


@rule("CH-22")
def ball_speeds(doc, ctx, p):
    t = T(doc)
    for e in doc["events"]:
        if e["type"] not in ("pass", "shot"):
            continue
        dur = e["tau1"] - e["tau0"]
        if dur <= 0:
            continue
        v = math.dist(e["p0"], e["p1"]) / dur
        kind = "shot" if e["type"] == "shot" else e["kind"]
        lo, hi = p[kind]
        if e.get("intercepted_by"):
            continue
        if not lo <= v <= hi:
            yield e["id"], f"{kind} travels at {v:.1f} m/s (realistic {lo}-{hi})"
    sp = np.linalg.norm(np.diff(t.B[:, :2], axis=0), axis=1) * FPS
    bad = [f for f in np.nonzero(sp > p["vmax"])[0] if (f + 1) not in t.cuts and t.pitch[f]]
    if bad:
        yield "ball", f"ball moves at {sp[bad[0]]:.1f} m/s at tau={bad[0] / FPS:.2f}s"


@rule("CH-23")
def pass_endpoints(doc, ctx, p):
    t = T(doc)
    for e in doc["events"]:
        if e["type"] != "pass":
            continue
        f0 = min(int(round(e["tau0"] * FPS)), t.n - 1)
        f1 = min(int(round(e["tau1"] * FPS)), t.n - 1)
        d0 = math.dist(e["p0"], t.P[e["from"]][f0])
        if d0 > p["max_m"]:
            yield e["id"], f"pass leaves {d0:.2f} m away from the passer {e['from']}"
        rcv = e.get("intercepted_by") or e.get("to")
        if rcv:
            d1 = math.dist(e["p1"], t.P[rcv][f1])
            if d1 > p["max_m"]:
                yield e["id"], f"pass arrives {d1:.2f} m away from {rcv}"


@rule("CH-24")
def pass_length(doc, ctx, p):
    for e in doc["events"]:
        if e["type"] == "pass" and not e.get("intercepted_by"):
            L = math.dist(e["p0"], e["p1"])
            fr = (e["tau1"] - e["tau0"]) * FPS
            if L < p["min_m"]:
                yield e["id"], f"pass is only {L:.1f} m long"
            if fr < p["min_frames"] - 0.5:
                yield e["id"], f"pass is in flight for only {fr:.0f} frames"


@rule("CH-25")
def possession_logic(doc, ctx, p):
    yield from _report(doc, "CH-25")


@rule("CH-26")
def interceptions(doc, ctx, p):
    yield from _report(doc, "CH-26")
    t = T(doc)
    for e in doc["events"]:
        if e["type"] == "intercept":
            f = min(int(round(e["tau0"] * FPS)), t.n - 1)
            d = math.dist(e["p0"], t.P[e["by"]][f])
            if d > p["max_m"]:
                yield e["id"], f"{e['by']} is {d:.2f} m from the ball at the interception"


@rule("CH-27")
def ball_in_bounds(doc, ctx, p):
    t = T(doc)
    m = p["margin"]
    shots = [(int(e["tau0"] * FPS), int(e["tau1"] * FPS) + 60) for e in doc["events"] if e["type"] == "shot"]
    out = np.nonzero((t.B[:, 0] < -m) | (t.B[:, 0] > 105 + m) | (t.B[:, 1] < -m) | (t.B[:, 1] > 68 + m))[0]
    bad = [f for f in out if t.pitch[f] and not any(a <= f <= b for a, b in shots)]
    if bad:
        yield "ball", f"ball leaves the pitch at tau={bad[0] / FPS:.2f}s"


@rule("CH-30")
def offside(doc, ctx, p):
    t = T(doc)
    for e in doc["events"]:
        if e["type"] != "pass" or not e.get("to"):
            continue
        rcv = e["to"]
        team = rcv[0]
        f = min(int(round(e["tau0"] * FPS)), t.n - 1)
        opp = [pid for pid in t.P if pid[0] != team]
        if team == "H":
            x_r, ball_x = t.P[rcv][f][0], e["p0"][0]
            line = sorted((t.P[o][f][0] for o in opp), reverse=True)[1]
            margin = line - x_r
            in_half = x_r > 52.5
            ahead = x_r > ball_x
        else:
            x_r, ball_x = t.P[rcv][f][0], e["p0"][0]
            line = sorted(t.P[o][f][0] for o in opp)[1]
            margin = x_r - line
            in_half = x_r < 52.5
            ahead = x_r < ball_x
        if in_half and ahead and margin < -p["tol"]:
            yield e["id"], f"{rcv} is offside by {-margin:.2f} m when the pass is played"
        elif in_half and ahead and margin < p["warn"]:
            yield e["id"], f"{rcv} is level with the last defender ({margin:.2f} m) — viewers may read it as offside", "warning"


# --------------------------------------------------------------------- overlays
@rule("CH-40")
def overlay_duration(doc, ctx, p):
    yield from _report(doc, "CH-40")
    for o in doc["overlays"]:
        d = o["tau_out"] - o["tau_in"]
        if d < p["min_s"]:
            yield o["id"], f"visible for {d:.2f} s (< {p['min_s']})"
        elif d < p["warn_s"]:
            yield o["id"], f"visible for only {d:.2f} s", "warning"


@rule("CH-41")
def text_readable(doc, ctx, p):
    for o in doc["overlays"]:
        if o.get("label"):
            need = max(p["min_s"], p["per_word"] * len(o["label"].split()) + p["base"])
            if o["tau_out"] - o["tau_in"] < need:
                yield o["id"], f"'{o['label']}' visible {o['tau_out'] - o['tau_in']:.2f} s; needs {need:.2f} s to read"


@rule("CH-42")
def clutter(doc, ctx, p):
    n = doc["tracks"]["n"]
    allc = np.zeros(n + 1, dtype=int)
    txt = np.zeros(n + 1, dtype=int)
    zones = np.zeros(n + 1, dtype=int)
    for o in doc["overlays"]:
        a, b = o["frame_in"], o["frame_out"]
        allc[a:b] += 1
        txt[a:b] += 1 if o.get("label") else 0
        zones[a:b] += 1 if o["kind"] == "zone" else 0
    for arr, lim, what in ((allc, p["max_all"], "overlays"), (txt, p["max_text"], "text overlays"), (zones, p["max_zones"], "zones")):
        if arr.max() > lim:
            f = int(arr.argmax())
            yield "overlays", f"{arr.max()} {what} at once at tau={f / FPS:.2f}s (max {lim})"


@rule("CH-43")
def arrow_lead(doc, ctx, p):
    plan = ctx.other("scene_plan")
    if not plan:
        return
    acts = {a["handle"]: a for a in doc["actions"]}
    ovs = {o["id"]: o for o in doc["overlays"]}
    for s in plan["scenes"]:
        for o in s.get("overlays", []) if s["kind"] == "pitch" else []:
            if o["kind"] == "run_arrow" and o.get("style", "preview") == "preview":
                a = acts.get(f"{s['id']}:{o['action']}")
                ov = ovs.get(f"{s['id']}:{o['id']}")
                if a is None or ov is None:
                    continue
                if a["tau0"] - ov["tau_in"] < p["lead_s"] - 1e-6:
                    yield ov["id"], f"preview arrow appears {a['tau0'] - ov['tau_in']:.2f} s before the run (needs {p['lead_s']} s)"


def _area(poly):
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


@rule("CH-44")
def zones_valid(doc, ctx, p):
    for o in doc["overlays"]:
        if o["kind"] != "zone":
            continue
        polys = [o["geom"]["static"]] if "static" in o["geom"] else o["geom"]["perFrame"]
        for poly in polys:
            if _area(poly) < p["min_area"]:
                yield o["id"], f"zone area {_area(poly):.1f} m^2 < {p['min_area']}"
                break
            if any(not (-1 <= x <= 106 and -1 <= y <= 69) for x, y in poly):
                yield o["id"], "zone extends outside the pitch"
                break


# --------------------------------------------------------------------- camera
@rule("CH-50")
def camera_bounds(doc, ctx, p):
    t = T(doc)
    if t.C is None:
        yield "camera_track", "missing"
        return
    yf, wf = _yfrac(doc), _w_fit(doc)
    m = p["margin"]
    for f in range(t.n):
        cx, cy, w = t.C[f]
        if w < p["min_w"] - 0.05 or w > wf + 0.05:
            yield "camera", f"zoom w={w:.1f} m at tau={f / FPS:.2f}s outside [{p['min_w']}, {wf:.1f}]"
            return
        hw, hh = w / 2, w * yf / 2
        # only an axis whose visible extent fits inside pitch+margins can be required to stay inside them
        bad_x = 2 * hw <= 105 + 2 * m and (cx - hw < -m - 0.05 or cx + hw > 105 + m + 0.05)
        bad_y = 2 * hh <= 68 + 2 * m and (cy - hh < -m - 0.05 or cy + hh > 68 + m + 0.05)
        if bad_x or bad_y:
            yield "camera", f"camera shows beyond the pitch margin at tau={f / FPS:.2f}s"
            return


@rule("CH-51")
def camera_speed(doc, ctx, p):
    t = T(doc)
    if t.C is None:
        return
    for f in range(1, t.n):
        if f in t.cuts or not t.pitch[f]:
            continue
        (x0, y0, w0), (x1, y1, w1) = t.C[f - 1], t.C[f]
        pan = math.hypot(x1 - x0, y1 - y0) * FPS
        zoom = abs(math.log(w1 / w0)) * FPS
        if pan > p["pan"] * w1 + 0.5:
            yield "camera", f"pans {pan:.1f} m/s at tau={f / FPS:.2f}s (max {p['pan'] * w1:.1f})"
            return
        if zoom > p["zoom"]:
            yield "camera", f"zooms too fast at tau={f / FPS:.2f}s ({zoom:.2f}/s)"
            return


def _featured(doc):
    out = []
    for e in doc["events"]:
        for k in ("from", "to", "by", "on"):
            if e.get(k):
                out.append((e[k], e["tau0"] - 0.3, e["tau1"] + 0.3))
    for o in doc["overlays"]:
        for pid in o.get("players", []):
            out.append((pid, o["tau_in"], o["tau_out"]))
    return out


@rule("CH-52")
def on_screen(doc, ctx, p):
    t = T(doc)
    if t.C is None:
        return
    yf = _yfrac(doc)
    s = p["safe"]
    shots = [(int(e["tau0"] * FPS), int(e["tau1"] * FPS) + 45) for e in doc["events"] if e["type"] == "shot"]

    def visible(x, y, f, k=1.0):
        cx, cy, w = t.C[f]
        return abs(x - cx) <= w * k / 2 and abs(y - cy) <= w * yf * k / 2
    for f in range(t.n):
        if t.pitch[f] and not any(a <= f <= b for a, b in shots) and not visible(t.B[f, 0], t.B[f, 1], f):
            yield "ball", f"ball off screen at tau={f / FPS:.2f}s"
            break
    for pid, a, b in _featured(doc):
        if pid not in t.P:
            continue
        frames = [f for f in range(max(int(a * FPS), 0), min(int(b * FPS), t.n)) if t.pitch[f]]
        if not frames:
            continue
        ok = sum(visible(*t.P[pid][f], f, s) for f in frames) / len(frames)
        if ok < p["share"]:
            yield pid, f"featured player {pid} inside the safe area only {ok:.0%} of tau {a:.1f}-{b:.1f}s"


@rule("CH-53")
def camera_jumps(doc, ctx, p):
    t = T(doc)
    if t.C is None:
        return
    for f in range(1, t.n):
        if f in t.cuts:
            continue
        (x0, y0, w0), (x1, y1, w1) = t.C[f - 1], t.C[f]
        if math.hypot(x1 - x0, y1 - y0) > p["max_jump_m"] or abs(w1 - w0) > 0.05 * w0:
            yield "camera", f"camera jumps at tau={f / FPS:.2f}s (not a cut boundary)"
            return


# --------------------------------------------------------------------- pacing
@rule("CH-60")
def dead_air(doc, ctx, p):
    marks = sorted({x for a in doc["actions"] for x in (a["tau0"], a["tau1"])}
                   | {x for e in doc["events"] for x in (e["tau0"], e["tau1"])}
                   | {x for o in doc["overlays"] for x in (o["tau_in"], o["tau_out"])}
                   | {k["tau"] for k in doc["camera_keys"]})
    for s in doc["scenes"]:
        if s["kind"] != "pitch":
            continue
        pts = [s["tau0"]] + [m for m in marks if s["tau0"] < m < s["tau0"] + s["len"]] + [s["tau0"] + s["len"]]
        gap = max(b - a for a, b in zip(pts, pts[1:]))
        if gap > p["max_s"]:
            yield s["id"], f"{gap:.1f} s with nothing happening"


@rule("CH-61")
def total_length(doc, ctx, p):
    brief = ctx.other("brief")
    if not brief:
        return
    total = doc["tracks"]["n"] / FPS
    target = brief["target_duration_s"]
    if not p["lo"] * target <= total <= p["hi"] * target:
        yield "scenes", f"authored length {total:.1f} s vs target {target} s (allowed {p['lo']}-{p['hi']} x)"
