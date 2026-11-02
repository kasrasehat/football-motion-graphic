"""Compile scene_plan + tactic_spec into choreography (dense 30 Hz tracks in authored time tau).

Per pitch scene we iterate a deterministic fixed point:
  1. resolve every time expression that can be resolved from the previous pass,
  2. simulate all 22 players (moves/carries: speed profiles along curved paths; press/mark/duel: pursuit
     integration with acceleration caps; idle: anchor + team block shift toward the ball + gentle sway),
  3. run ball events in time order (passes with a receiver fixed-point, intercepts, tackles, shots),
     build the possession timeline and the ball track,
until times and tracks stop changing. Problems become report errors tagged with CH rule ids; the validators
then re-check physics independently on the dense tracks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from tms.choreo import motion as M
from tms.choreo.motion import DT, FPS, P
from tms.tactic import formations as F
from tms.tactic.geometry import LENGTH, WIDTH, to_abs, zone_point

HORIZON_S = 24.0
MAX_ITER = 14
TAIL_S = 1.2
GRAPHIC_DEFAULT_S = 4.0
LATERAL_GAIN = 0.6


class CompileError(Exception):
    pass


def attack_dir(team: str) -> float:
    return 1.0 if team == "H" else -1.0


def own_goal(team: str) -> P:
    return (0.0, WIDTH / 2) if team == "H" else (LENGTH, WIDTH / 2)


def opp_goal_x(team: str) -> float:
    return LENGTH if team == "H" else 0.0


@dataclass
class SceneResult:
    id: str
    kind: str
    n: int                                   # frames
    players: dict[str, list[P]]              # per-frame positions
    ball: list[tuple[float, float, float]]   # per-frame x,y,z
    events: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    possession: list[dict] = field(default_factory=list)
    holds: list[dict] = field(default_factory=list)
    reveals: list[dict] = field(default_factory=list)
    times: dict[str, tuple[float, float]] = field(default_factory=dict)  # ref -> (start, end)
    holder_end: str = ""
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    plan: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- time expressions
def handle_of(a: dict, counters: dict) -> str | None:
    kind = a["type"]
    if kind in ("move", "carry", "press", "mark"):
        pid = a["player"]
    elif kind == "duel":
        pid = a["players"][0]
    else:
        return None
    key = (pid, kind)
    counters[key] = counters.get(key, 0) + 1
    return f"{pid}@{kind}#{counters[key]}"


def eval_time(expr, times: dict, scene_end: float | None):
    """Resolve a time expression -> seconds or None (not yet resolvable)."""
    if expr is None:
        return None
    if isinstance(expr, (int, float)):
        return float(expr)
    if expr == "scene.end":
        return scene_end
    if "after" in expr:
        ref, use = expr["after"], "end"
        sign = 1.0
    else:
        ref, use = expr["before"], "start"
        sign = -1.0
    if ref == "scene.end":
        base = scene_end
    else:
        if "." in ref and ref.split(".")[-1] in ("start", "end"):
            ref, use = ref.rsplit(".", 1)
        if ref not in times:
            return None
        base = times[ref][0 if use == "start" else 1]
    if base is None:
        return None
    return max(0.0, base + sign * float(expr["plus"]))


# ----------------------------------------------------------------------------- scene simulation
class SceneSim:
    def __init__(self, scene: dict, start: dict[str, P], holder: str, spec: dict, horizon_s: float = HORIZON_S,
                 start_vel: dict[str, P] | None = None, ball0: P | None = None):
        self.scene = scene
        self.start = start
        self.start_vel = start_vel or {}
        self.ball0 = ball0
        self.holder0 = holder
        self.spec = spec
        self.N = int(horizon_s * FPS) + 1
        self.team = {pid: pid[0] for pid in start}
        self.gk = {t: next(p["id"] for p in spec["teams"][t]["players"] if p["role"] == "GK") for t in "HA"}
        self.block_shift = {t: spec["teams"][t]["shape"]["block"]["ball_shift"] for t in "HA"}
        counters: dict = {}
        self.actions = []
        for i, a in enumerate(scene.get("actions", [])):
            self.actions.append({"i": i, "a": a, "handle": handle_of(a, counters)})
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.paths: dict[str, list[list[float]]] = {}

    # --- helpers
    def err(self, rule: str, msg: str):
        e = {"rule": rule, "scene": self.scene["id"], "message": msg}
        if e not in self.errors:
            self.errors.append(e)

    def frame(self, t: float) -> int:
        return min(max(int(round(t * FPS)), 0), self.N - 1)

    def target_point(self, pid: str, tgt: dict, t: float, tracks) -> P:
        if "pitch" in tgt:
            return (float(tgt["pitch"][0]), float(tgt["pitch"][1]))
        if "zone" in tgt:
            return to_abs(self.team[pid], zone_point(tgt["zone"]))
        other = tgt["rel_player"]
        base = tracks[other][self.frame(t)] if other in tracks else self.start[other]
        dx, dy = tgt["offset"]
        return (base[0] + dx * attack_dir(self.team[other]), base[1] + dy * attack_dir(self.team[other]))

    def deps(self) -> dict[str, set[str]]:
        d = {pid: set() for pid in self.start}
        for x in self.actions:
            a = x["a"]
            if a["type"] in ("move", "carry") and "rel_player" in a["to"]:
                d[a["player"]].add(a["to"]["rel_player"])
            elif a["type"] == "press":
                d[a["player"]] |= {a["on"]} | ({a["cut"]} if a.get("cut") else set())
            elif a["type"] == "mark":
                d[a["player"]].add(a["on"])
            elif a["type"] == "duel":
                p, q = a["players"]
                d[p].add(q)
        return d

    def order(self) -> list[str]:
        deps = self.deps()
        out, mark = [], {}

        def visit(n, stack):
            if mark.get(n) == 2:
                return
            if mark.get(n) == 1:
                self.err("CH-02", f"circular player dependency: {' -> '.join(stack + [n])}")
                return
            mark[n] = 1
            for m in sorted(deps.get(n, ())):
                if m in self.start:
                    visit(m, stack + [n])
            mark[n] = 2
            out.append(n)
        for n in sorted(self.start):
            visit(n, [])
        return out

    # --- one pass
    def simulate(self, times: dict, ball_prev: list | None) -> tuple[dict, dict]:
        """Returns (tracks, handle_times)."""
        N = self.N
        tracks: dict[str, list[P]] = {}
        handle_times: dict[str, tuple[float, float]] = {}
        shape_keys = self._shape_keys(times)
        ball_y0 = self.start[self.holder0][1]
        for pid in self.order():
            team = self.team[pid]
            intents = []
            for x in self.actions:
                a = x["a"]
                actor = a.get("player") or (a["players"][0] if a["type"] == "duel" else None)
                if a["type"] == "duel" and pid in a["players"]:
                    actor = pid
                if actor != pid or a["type"] not in ("move", "carry", "press", "mark", "duel"):
                    continue
                t0 = eval_time(a.get("at", a.get("from")), times, None)
                if t0 is None:
                    continue
                intents.append((t0, x))
            intents.sort(key=lambda z: (z[0], z[1]["i"]))
            pos = self.start[pid]
            vel = self.start_vel.get(pid, (0.0, 0.0))
            arr: list[P] = []
            anchor, anchor_t = pos, 0.0
            anchor_by = ball_y0  # ball y when the current idle period began (no jump when a move ends)
            k = 0
            cur = None  # (kind, data)
            for f in range(N):
                t = f * DT
                while k < len(intents) and intents[k][0] <= t + 1e-9:
                    t0, x = intents[k]
                    cur = self._start_intent(pid, x, t0, pos, vel, tracks, times, handle_times)
                    k += 1
                if cur is not None:
                    kind, data = cur
                    if kind == "path":
                        u = t - data["t0"]
                        if u >= data["prof"].T:
                            pos = data["path"].b
                            vel = (0.0, 0.0)
                            anchor, anchor_t = pos, t
                            anchor_by = self._lag_y(ball_prev, f, shape_keys, team, ball_y0)
                            cur = None
                        else:
                            np_ = data["path"].at_distance(data["prof"].s(u))
                            vel = M.mul(M.sub(np_, pos), FPS)
                            pos = np_
                        arr.append(pos)
                        continue
                    if kind in ("press", "mark", "duel"):
                        if data["until"] is not None and t > data["until"]:
                            cur = None
                            anchor, anchor_t = pos, t
                            anchor_by = self._lag_y(ball_prev, f, shape_keys, team, ball_y0)
                        else:
                            tgt = self._pursuit_target(pid, kind, data, f, tracks)
                            pos, vel = M.pursue(pos, vel, tgt, data["vmax"])
                            arr.append(pos)
                            continue
                # idle: anchor + team block reaction to the (lagged) ball + sway
                bs = self._shift_at(team, t, shape_keys)
                react = shape_keys[team][-1][2] if shape_keys.get(team) else 0.4
                by_l = ball_prev[max(f - int(react * FPS), 0)][1] if ball_prev else ball_y0
                gain = LATERAL_GAIN * (0.3 if pid == self.gk[team] else 1.0)
                shift_y = gain * bs * (by_l - anchor_by)
                d = M.drift(pid, t)
                d0 = M.drift(pid, anchor_t)
                tgt = (anchor[0] + d[0] - d0[0], min(max(anchor[1] + shift_y + d[1] - d0[1], 0.5), WIDTH - 0.5))
                pos, vel = M.pursue(pos, vel, tgt, 3.5, tau=0.8, accel=2.5)
                arr.append(pos)
            tracks[pid] = arr
        return tracks, handle_times

    @staticmethod
    def _lag_y(ball_prev, f, shape_keys, team, default):
        if not ball_prev:
            return default
        react = shape_keys[team][-1][2] if shape_keys.get(team) else 0.4
        return ball_prev[max(f - int(react * FPS), 0)][1]

    def _shape_keys(self, times) -> dict:
        keys: dict[str, list] = {}
        for s in self.scene.get("shape", []):
            t = eval_time(s["at"], times, None)
            if t is None:
                continue
            bs = (s.get("block") or {}).get("ball_shift")
            keys.setdefault(s["team"], []).append((t, bs, s.get("react_s", 0.4)))
        for v in keys.values():
            v.sort(key=lambda z: z[0])
        return keys

    def _shift_at(self, team, t, keys) -> float:
        bs = self.block_shift[team]
        for (kt, kbs, _) in keys.get(team, []):
            if kt <= t and kbs is not None:
                bs = kbs
        return bs

    def _start_intent(self, pid, x, t0, pos, vel, tracks, times, handle_times):
        a, h = x["a"], x["handle"]
        if a["type"] in ("move", "carry"):
            pace = M.PACE[a["pace"]]
            tgt = self.target_point(pid, a["to"], t0, tracks)
            # only the velocity component along the new direction carries over into the speed profile
            v0 = max(0.0, vel[0] * M.unit(M.sub(tgt, pos))[0] + vel[1] * M.unit(M.sub(tgt, pos))[1])
            for _ in range(3):  # aim where a moving reference player will be on arrival
                path = M.Path(pos, tgt, a.get("curve_m", 0.0))
                prof = M.Profile(path.length, pace, v0)
                if "rel_player" not in a["to"]:
                    break
                tgt = self.target_point(pid, a["to"], t0 + prof.T, tracks)
            path = M.Path(pos, tgt, a.get("curve_m", 0.0))
            prof = M.Profile(path.length, pace, v0)
            handle_times[h] = (t0, t0 + prof.T)
            self.paths[h] = [[round(p[0], 2), round(p[1], 2)] for p in path.polyline(16)]
            return ("path", {"t0": t0, "path": path, "prof": prof, "handle": h})
        until_expr = a.get("until")
        until = eval_time(until_expr, times, None) if until_expr is not None else None
        if a["type"] == "press":
            data = {"on": a["on"], "cut": a.get("cut"), "vmax": M.PACE[a["pace"]], "until": until}
        elif a["type"] == "mark":
            data = {"on": a["on"], "dist": a.get("dist_m", 1.5), "goal_side": a.get("goal_side", True),
                    "vmax": M.PACE["sprint"], "until": until}
        else:
            other = a["players"][1] if a["players"][0] == pid else a["players"][0]
            data = {"on": other, "vmax": M.PACE["run"], "until": until}
        handle_times[h] = (t0, until if until is not None else HORIZON_S)
        return (a["type"], data)

    def _pursuit_target(self, pid, kind, data, f, tracks) -> P:
        on = tracks.get(data["on"], [self.start[data["on"]]] * (f + 1))
        c = on[min(f, len(on) - 1)]
        team = self.team[pid]
        if kind == "press":
            if data.get("cut") and data["cut"] in tracks:
                x = tracks[data["cut"]][min(f, len(tracks[data["cut"]]) - 1)]
                return M.add(c, M.mul(M.unit(M.sub(x, c)), 1.6))
            return M.add(c, M.mul(M.unit(M.sub(own_goal(team), c)), 1.4))
        if kind == "mark":
            return M.add(c, M.mul(M.unit(M.sub(own_goal(team), c)), data["dist"]))
        return M.add(c, M.mul(M.unit(M.sub(self.start[pid], c), (0.0, 1.0)), 1.0))

    # --- ball
    def ball_events(self, tracks: dict, times: dict, handle_times: dict):
        """Run ball events in order; returns (ball track, possession segments, event records, corrections)."""
        evs = []
        for x in self.actions:
            a = x["a"]
            if a["type"] in ("pass", "tackle", "shot"):
                t0 = eval_time(a["at"], times, None)
                if t0 is not None:
                    evs.append((t0, x))
            elif a["type"] == "intercept":
                pt = times.get(a["pass"])
                if pt is not None:
                    evs.append((pt[0] + 1e-6, x))
        evs.sort(key=lambda z: (z[0], z[1]["i"]))
        holder = self.holder0
        segs = []  # (t0, t1, state, by, event, data)
        seg_start = 0.0
        records = []
        event_times = {}
        intercepted = {x["a"]["pass"]: x for x in self.actions if x["a"]["type"] == "intercept"}
        cut_after = None

        def ballpos(pid, f):
            p = tracks[pid][f]
            prev = tracks[pid][max(f - 3, 0)]
            v = M.sub(p, prev)
            d = M.unit(v) if M.norm(v) > 0.08 else (attack_dir(self.team[pid]), 0.0)
            return M.add(p, M.mul(d, 0.7))

        loose = {"pt": None}

        def pickup(until_t):
            """A loose ball becomes held by the first player within 1.2 m (before until_t)."""
            nonlocal holder, seg_start
            if holder is not None or loose["pt"] is None or cut_after is not None:
                return
            for f in range(self.frame(seg_start), min(self.frame(until_t), self.N - 1) + 1):
                pid, d = min(((p, M.norm(M.sub(tracks[p][f], loose["pt"]))) for p in tracks), key=lambda z: z[1])
                if d <= 1.2:
                    segs.append((seg_start, f * DT, "loose", None, None, {"at": loose["pt"], "span": True}))
                    holder, seg_start, loose["pt"] = pid, f * DT, None
                    return

        for t0, x in evs:
            a = x["a"]
            pickup(t0)
            if cut_after is not None and t0 > cut_after:
                self.err("CH-25", f"{a.get('id', a['type'])} happens after the ball went dead")
                continue
            if a["type"] != "intercept" and t0 < seg_start - 1e-6:
                self.err("CH-25", f"{a.get('id', a['type'])} at {t0:.2f}s happens before the ball reaches "
                                  f"{holder or 'anyone'} ({seg_start:.2f}s) — time it {{'after': <previous event>}}")
                continue
            f0 = self.frame(t0)
            if a["type"] == "pass":
                if holder != a["from"]:
                    self.err("CH-25", f"{a['id']}: {a['from']} passes at {t0:.2f}s but {holder or 'nobody'} has the ball")
                    continue
                rel = ballpos(a["from"], f0)
                speed = M.PASS_SPEED[a["kind"]]
                if "to" in a:
                    rcv = a["to"]
                    t1 = t0 + M.norm(M.sub(tracks[rcv][f0], rel)) / speed
                    for _ in range(5):
                        f1 = self.frame(t1)
                        rp = tracks[rcv][f1]
                        rv = M.sub(rp, tracks[rcv][max(f1 - 3, 0)])
                        # a moving receiver is met where he will be (that IS the lead); a static one steps onto it
                        lead = 0.0 if M.norm(rv) > 0.1 else a.get("lead_m", 0.0)
                        arr_pt = M.add(rp, M.mul((attack_dir(self.team[rcv]), 0.0), lead))
                        t1 = t0 + max(M.norm(M.sub(arr_pt, rel)) / speed, 8 * DT)
                    f1 = self.frame(t1)
                else:
                    rcv = None
                    arr_pt = (float(a["to_point"][0]), float(a["to_point"][1]))
                    t1 = t0 + max(M.norm(M.sub(arr_pt, rel)) / speed, 8 * DT)
                if a["id"] in intercepted:
                    ix = intercepted[a["id"]]
                    by = ix["a"]["by"]
                    hit = None
                    for f in range(f0 + 1, self.frame(t1) + 1):
                        u = (f - f0) / max(self.frame(t1) - f0, 1)
                        bp = M.lerp(rel, arr_pt, u)
                        if M.norm(M.sub(tracks[by][f0], bp)) / M.PACE["sprint"] <= (f - f0) * DT + 0.15:
                            hit = (f, bp)
                            break
                    if hit is None:
                        self.err("CH-26", f"{ix['a']['id']}: {by} cannot reach pass {a['id']} in time")
                    else:
                        fi, bp = hit
                        segs.append((seg_start, t0, "held", holder, None, None))
                        segs.append((t0, fi * DT, "flight", None, a["id"], {"from": rel, "to": bp, "kind": a["kind"]}))
                        records.append({"id": a["id"], "type": "pass", "from": a["from"], "to": rcv, "tau0": t0,
                                        "tau1": fi * DT, "p0": list(rel), "p1": list(bp), "kind": a["kind"], "intercepted_by": by})
                        records.append({"id": ix["a"]["id"], "type": "intercept", "by": by, "pass": a["id"],
                                        "tau0": fi * DT, "tau1": fi * DT, "p0": list(bp), "p1": list(bp)})
                        event_times[a["id"]] = (t0, fi * DT)
                        event_times[ix["a"]["id"]] = (fi * DT, fi * DT)
                        self._correct(tracks, by, f0, fi, bp, radius=0.6)
                        holder, seg_start = by, fi * DT
                        continue
                segs.append((seg_start, t0, "held", holder, None, None))
                segs.append((t0, t1, "flight", None, a["id"], {"from": rel, "to": arr_pt, "kind": a["kind"]}))
                records.append({"id": a["id"], "type": "pass", "from": a["from"], "to": rcv, "tau0": t0, "tau1": t1,
                                "p0": list(rel), "p1": list(arr_pt), "kind": a["kind"]})
                event_times[a["id"]] = (t0, t1)
                if rcv is not None:
                    self._correct(tracks, rcv, max(self.frame(t1) - 15, f0), self.frame(t1), arr_pt, radius=0.6)
                    holder, seg_start = rcv, t1
                else:
                    holder, seg_start, loose["pt"] = None, t1, arr_pt
            elif a["type"] == "tackle":
                if holder != a["on"]:
                    self.err("CH-25", f"{a['id']}: tackle on {a['on']} at {t0:.2f}s but {holder or 'nobody'} has the ball")
                    continue
                gap = M.norm(M.sub(tracks[a["by"]][f0], tracks[a["on"]][f0]))
                if gap > 4.0:
                    self.err("CH-25", f"{a['id']}: {a['by']} is {gap:.1f} m from {a['on']} at the tackle — press first")
                    continue
                self._correct(tracks, a["by"], max(f0 - 12, 0), f0, tracks[a["on"]][f0], radius=1.0)
                segs.append((seg_start, t0, "held", holder, None, None))
                records.append({"id": a["id"], "type": "tackle", "by": a["by"], "on": a["on"], "tau0": t0, "tau1": t0,
                                "p0": list(tracks[a["on"]][f0]), "p1": list(tracks[a["on"]][f0])})
                event_times[a["id"]] = (t0, t0)
                holder, seg_start = a["by"], t0
            elif a["type"] == "shot":
                if holder != a["by"]:
                    self.err("CH-25", f"{a['id']}: {a['by']} shoots at {t0:.2f}s but {holder or 'nobody'} has the ball")
                    continue
                team = self.team[a["by"]]
                rel = ballpos(a["by"], f0)
                gx = opp_goal_x(team)
                near = 30.34 + 1.0 if rel[1] < WIDTH / 2 else 37.66 - 1.0
                far = 37.66 - 1.0 if rel[1] < WIDTH / 2 else 30.34 + 1.0
                gy = {"near_post": near, "far_post": far, "centre": WIDTH / 2}[a["aim"]]
                if a["outcome"] == "wide":
                    gy = 30.34 - 1.5 if gy < WIDTH / 2 else 37.66 + 1.5
                end = (gx + attack_dir(team) * (0.8 if a["outcome"] == "goal" else 0.0), gy)
                if a["outcome"] == "blocked":
                    end = M.lerp(rel, end, 0.35)
                t1 = t0 + max(M.norm(M.sub(end, rel)) / M.SHOT_SPEED, 8 * DT)
                segs.append((seg_start, t0, "held", holder, None, None))
                segs.append((t0, t1, "flight", None, a["id"], {"from": rel, "to": end, "kind": "shot"}))
                records.append({"id": a["id"], "type": "shot", "by": a["by"], "tau0": t0, "tau1": t1, "p0": list(rel),
                                "p1": list(end), "outcome": a["outcome"], "aim": a["aim"]})
                event_times[a["id"]] = (t0, t1)
                if a["outcome"] == "saved":
                    gk = self.gk["A" if team == "H" else "H"]
                    self._correct(tracks, gk, f0, self.frame(t1), end, radius=0.5)
                    holder, seg_start = gk, t1
                elif a["outcome"] == "blocked":
                    holder, seg_start, loose["pt"] = None, t1, end
                else:
                    holder, seg_start = None, t1
                    segs.append((t1, t1, "dead", None, None, {"at": end}))
                    cut_after = t1
        pickup(self.N * DT)
        # carries by non-holders
        for x in self.actions:
            a = x["a"]
            if a["type"] == "carry" and x["handle"] in handle_times:
                t0 = handle_times[x["handle"]][0]
                h = self._holder_at(segs, holder, seg_start, t0)
                if h != a["player"]:
                    self.err("CH-25", f"{x['handle']}: {a['player']} carries at {t0:.2f}s but {h or 'nobody'} has the ball")
        if holder is not None:
            segs.append((seg_start, None, "held", holder, None, None))
        elif cut_after is None:
            segs.append((seg_start, None, "loose", None, None, {"at": loose["pt"], "span": True}))
        else:
            segs.append((seg_start, None, "dead", None, None, {"at": segs[-1][5]["at"] if segs[-1][5] else (52.5, 34), "span": True}))
        ball, poss = self._ball_track(segs, tracks, ballpos)
        return ball, poss, records, event_times, holder

    @staticmethod
    def _holder_at(segs, final_holder, final_start, t):
        for (a, b, st, by, _, _) in segs:
            if st == "held" and a <= t + 1e-9 and (b is None or t < b):
                return by
        return final_holder if t >= final_start else None

    CORRECT_ACCEL = 2.5  # m/s^2 peak added by a correction (smoothstep peak = 6 d / T^2)

    def _correct(self, tracks, pid, fa, fb, point: P, radius: float):
        """Blend pid's track so it is within `radius` of `point` at frame fb. The blend starts early enough
        (never later than `fa`) that the added acceleration stays below CORRECT_ACCEL."""
        fb = min(fb, self.N - 1)
        cur = tracks[pid][fb]
        off = M.sub(point, cur)
        d = M.norm(off)
        if d <= radius:
            return
        shift = d - radius * 0.5
        delta = M.mul(M.unit(off), shift)
        need = int(math.ceil(math.sqrt(6 * shift / self.CORRECT_ACCEL) * FPS))
        fa = max(0, min(fa, fb - need))
        span = max(fb - fa, 1)
        for f in range(fa, self.N):
            u = 1.0 if f >= fb else (f - fa) / span
            k = u * u * (3 - 2 * u)
            p = tracks[pid][f]
            tracks[pid][f] = (p[0] + delta[0] * k, p[1] + delta[1] * k)

    def _ball_track(self, segs, tracks, ballpos):
        N = self.N
        ball = [None] * N
        poss = []
        loose_at = None
        prev_end = self.ball0  # continuity with the previous scene's ball
        for (a, b, st, by, ev, data) in segs:
            fa = self.frame(a)
            fb = N if b is None else self.frame(b)
            if st == "held":
                poss.append({"tau0": a, "tau1": b, "state": "held", "by": by, "event": None})
                # ball sits 0.7 m in front of the carrier; the direction turns smoothly (no 40 m/s flicks)
                d = (attack_dir(self.team[by]), 0.0)
                if fa > 0:
                    v0 = M.sub(tracks[by][fa], tracks[by][max(fa - 4, 0)])
                    if M.norm(v0) > 0.1:
                        d = M.unit(v0)
                for f in range(fa, fb):
                    p = tracks[by][f]
                    v = M.sub(p, tracks[by][max(f - 4, 0)])
                    want = M.unit(v) if M.norm(v) > 0.13 else d
                    d = M.unit(M.add(d, M.mul(M.sub(want, d), 0.12)), d)
                    bp = M.add(p, M.mul(d, 0.7))
                    if prev_end is not None and f - fa < 6:  # receive: settle from the arrival point
                        k = (f - fa + 1) / 6
                        bp = M.lerp(prev_end, bp, k * k * (3 - 2 * k))
                    ball[f] = (bp[0], bp[1], 0.11)
                prev_end = None
            elif st == "flight":
                poss.append({"tau0": a, "tau1": b, "state": "flight", "by": None, "event": ev})
                n = max(fb - fa, 1)
                L = M.norm(M.sub(data["to"], data["from"]))
                peak = {"ground": 0.0, "driven": 0.6, "through": 0.2, "lofted": min(0.13 * L, 12.0),
                        "cross": min(0.1 * L, 7.0), "shot": 0.8}[data["kind"]]
                for f in range(fa, fb):
                    u = (f - fa) / n
                    s = (u - 0.12 * u * u) / 0.88  # slight deceleration
                    p = M.lerp(data["from"], data["to"], s)
                    ball[f] = (p[0], p[1], 0.11 + 4 * peak * u * (1 - u))
                prev_end = data["to"]
            elif st in ("loose", "dead"):
                loose_at = data["at"]
                span = bool(data and data.get("span"))
                poss.append({"tau0": a, "tau1": b if span else a, "state": st, "by": None, "event": None})
                if loose_at is not None:
                    for f in range(fa, fb):
                        ball[f] = (loose_at[0], loose_at[1], 0.11)
                prev_end = loose_at
        last = None
        for f in range(N):
            if ball[f] is None:
                ball[f] = last if last is not None else (loose_at[0], loose_at[1], 0.11) if loose_at else (LENGTH / 2, WIDTH / 2, 0.11)
            last = ball[f]
        # loose balls: the first player within 1.2 m picks it up (shown as held from then on)
        merged = []
        for i, p in enumerate(poss):
            if p["tau1"] is None:
                p = dict(p, tau1=None)
            merged.append(p)
        return ball, merged

    # --- fixed point
    def run(self) -> SceneResult:
        times: dict[str, tuple[float, float]] = {}
        ball_prev = None
        tracks = handle_times = None
        records = poss = None
        holder_end = self.holder0
        for it in range(MAX_ITER):
            self.errors = []
            tracks, handle_times = self.simulate(times, ball_prev)
            ball, poss, records, event_times, holder_end = self.ball_events(tracks, times, handle_times)
            new_times = {**handle_times, **event_times}
            stable = set(new_times) == set(times) and all(
                abs(new_times[k][0] - times[k][0]) < 1e-3 and abs((new_times[k][1] or 0) - (times[k][1] or 0)) < 1e-3
                for k in new_times)
            ball_stable = ball_prev is not None and max(abs(a[1] - b[1]) for a, b in zip(ball, ball_prev)) < 0.02
            times, ball_prev = new_times, ball
            if stable and ball_stable:
                break
        refs = self._all_refs()
        unresolved = sorted(r for r in refs if r.split(".")[0] not in times and r != "scene.end")
        for r in unresolved:
            self.err("CH-02", f"time reference {r!r} never resolves (unknown id/handle or circular timing)")
        # scene length
        content_end = 0.0
        for (t0, t1) in times.values():
            for v in (t0, t1):
                if v is not None and v < HORIZON_S - 0.5:
                    content_end = max(content_end, v)
        for h in self.scene.get("holds", []):
            ht = eval_time(h["at"], times, None)
            if ht is not None:
                content_end = max(content_end, ht)
        for key in ("overlays", "camera"):
            for o in self.scene.get(key, []):
                for fld in ("in", "out", "at"):
                    v = o.get(fld)
                    if isinstance(v, (int, float)):
                        content_end = max(content_end, float(v) + (o.get("dur_s", 0) if fld == "at" else 0))
        auto_len = max(content_end + TAIL_S, 2.0)
        L = self.scene.get("length_s")
        if L is None:
            L = auto_len
        elif L + 1e-6 < content_end:
            self.err("CH-01", f"length_s={L} but content runs until {content_end:.2f} s")
        n = int(round(L * FPS))
        if n >= self.N:
            self.err("CH-01", f"scene longer than the {HORIZON_S:.0f} s simulation horizon")
            n = self.N - 1
        holds = []
        for h in self.scene.get("holds", []):
            ht = eval_time(h["at"], times, L)
            if ht is None:
                self.err("CH-02", f"hold {h['id']} time never resolves")
                continue
            holds.append({"id": h["id"], "tau": round(min(ht, L), 4), "max_s": h["max_s"], "style": h["style"]})
        actions = [{"handle": f"{self.scene['id']}:{h}", "scene": self.scene["id"], "tau0": round(v[0], 4),
                    "tau1": round(min(v[1], L), 4)} for h, v in handle_times.items()]
        for rec in actions:
            pid = rec["handle"].split(":")[1].split("@")[0]
            fa, fb = self.frame(rec["tau0"]), self.frame(rec["tau1"])
            path_m = sum(M.norm(M.sub(tracks[pid][f + 1], tracks[pid][f])) for f in range(fa, min(fb, self.N - 1)))
            rec["path_m"] = round(path_m, 2)
        res = SceneResult(
            id=self.scene["id"], kind="pitch", n=n,
            players={pid: tr[: n + 1] for pid, tr in tracks.items()},
            ball=ball_prev[: n + 1], events=records, actions=actions, possession=poss, holds=holds,
            times={**times}, holder_end=self._holder_at_frame(poss, n * DT) or holder_end or self.holder0,
            errors=list(self.errors), warnings=list(self.warnings), plan=self.scene)
        res.final_positions = {pid: tr[n] for pid, tr in tracks.items()}  # type: ignore[attr-defined]
        res.paths = dict(self.paths)  # type: ignore[attr-defined]
        res.final_vel = {pid: M.mul(M.sub(tr[n], tr[max(n - 1, 0)]), FPS) for pid, tr in tracks.items()}  # type: ignore[attr-defined]
        return res

    @staticmethod
    def _holder_at_frame(poss, t):
        h = None
        for p in poss:
            if p["state"] == "held" and p["tau0"] <= t + 1e-9:
                h = p["by"]
        return h

    def _all_refs(self) -> set[str]:
        refs = set()

        def walk(v):
            if isinstance(v, dict):
                for k in ("after", "before"):
                    if k in v:
                        refs.add(v[k].rsplit(".", 1)[0] if v[k].endswith((".start", ".end")) else v[k])
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(self.scene.get("actions", []))
        walk(self.scene.get("holds", []))
        walk(self.scene.get("overlays", []))
        walk(self.scene.get("camera", []))
        return refs


# ----------------------------------------------------------------------------- global assembly
def snapshot_positions(spec: dict) -> dict[str, P]:
    out = {}
    for t in "HA":
        for p in spec["teams"][t]["players"]:
            out[p["id"]] = to_abs(t, (float(p["pos"][0]), float(p["pos"][1])))
    return out


def compile_plan(plan: dict, spec: dict) -> dict:
    """Return the in-memory compilation (scene results + global tracks). See build_doc for the artifact."""
    snap = snapshot_positions(spec)
    starts: dict[str, dict] = {}
    state = dict(snap)
    for pid, xy in plan["start"]["overrides"].items():
        state[pid] = (float(xy[0]), float(xy[1]))
    holder = spec["ball"]["holder"]
    vel: dict[str, P] = {}
    ball0: P | None = None
    results: list[SceneResult] = []
    errors, warnings = [], []
    ids = [s["id"] for s in plan["scenes"]]
    if len(ids) != len(set(ids)):
        errors.append({"rule": "CH-02", "scene": None, "message": "duplicate scene ids"})
    for sc in plan["scenes"]:
        starts[sc["id"]] = {"state": dict(state), "holder": holder}
        if sc["kind"] == "pitch" and sc["transition"] == "reset":
            ref = sc.get("reset_to") or "tactic_snapshot"
            vel, ball0 = {}, None
            if ref == "tactic_snapshot":
                state, holder = dict(snap), spec["ball"]["holder"]
            elif ref.endswith(":start") and ref[:-6] in starts:
                st = starts[ref[:-6]]
                state, holder = dict(st["state"]), st["holder"]
            else:
                errors.append({"rule": "CH-02", "scene": sc["id"], "message": f"reset_to {ref} is not an earlier scene"})
            starts[sc["id"]] = {"state": dict(state), "holder": holder}
        if sc["kind"] == "graphic":
            n = int(round((sc.get("length_s") or GRAPHIC_DEFAULT_S) * FPS))
            bx, by = state[holder]
            res = SceneResult(id=sc["id"], kind="graphic", n=n,
                              players={pid: [p] * (n + 1) for pid, p in state.items()},
                              ball=[(bx + 0.7, by, 0.11)] * (n + 1), holder_end=holder, plan=sc,
                              reveals=[{"id": r["id"], "tau": r["at"]} for r in sc.get("reveals", [])],
                              possession=[{"tau0": 0.0, "tau1": None, "state": "held", "by": holder, "event": None}])
            res.final_positions = dict(state)  # type: ignore[attr-defined]
        else:
            res = SceneSim(sc, state, holder, spec, start_vel=vel, ball0=ball0).run()
            state, holder = dict(res.final_positions), res.holder_end  # type: ignore[attr-defined]
            vel = res.final_vel  # type: ignore[attr-defined]
            ball0 = (res.ball[res.n][0], res.ball[res.n][1])
        results.append(res)
        errors += res.errors
        warnings += res.warnings
    return {"scenes": results, "errors": errors, "warnings": warnings}
