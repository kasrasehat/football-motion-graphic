"""Assemble the choreography artifact (build/choreography.json) from compiled scenes."""
from __future__ import annotations

from tms import jsonio
from tms.choreo import camera as C
from tms.choreo.compile import SceneResult, compile_plan, eval_time
from tms.choreo.motion import DT, FPS
from tms.tactic.geometry import LENGTH, WIDTH, ZONES, to_abs

STYLE = {
    "run_arrow": {"color": "accent", "dash": True, "fill": False, "curved": True},
    "pass_line": {"color": "ink", "dash": True, "fill": False},
    "zone": {"color": "warn", "dash": False, "fill": True},
    "line": {"color": "ink", "dash": True, "fill": False},
    "ring": {"color": "accent", "dash": False, "fill": False},
    "spotlight": {"color": "accent", "dash": False, "fill": False},
    "label": {"color": "ink", "dash": False, "fill": True},
    "distance": {"color": "accent", "dash": False, "fill": False},
    "polygon": {"color": "accent", "dash": False, "fill": False},
}
THIRDS = {"def": (0.0, 35.0), "mid": (35.0, 70.0), "att": (70.0, 105.0)}
CHANNELS = {"l_wide": (0.0, 13.84), "l_half_space": (13.84, 24.84), "centre": (24.84, 43.16),
            "r_half_space": (43.16, 54.16), "r_wide": (54.16, 68.0)}


def _r(p):
    return [round(p[0], 2), round(p[1], 2)]


def named_rect(name: str, team: str) -> list[list[float]]:
    if name in ("zone14",):
        x0, x1, y0, y1 = 70.0, 88.5, 24.84, 43.16
    elif name in ("box",):
        x0, x1, y0, y1 = 88.5, 105.0, 13.84, 54.16
    else:
        ch, _, th = name.rpartition("_")
        if ch not in CHANNELS or th not in THIRDS:
            c = ZONES.get(name, (52.5, 34.0))
            x0, x1, y0, y1 = c[0] - 6, c[0] + 6, c[1] - 6, c[1] + 6
        else:
            (x0, x1), (y0, y1) = THIRDS[th], CHANNELS[ch]
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [_r(to_abs(team, c)) for c in corners]


def convex_hull(points):
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def def_line_x(res: SceneResult, team: str, f: int) -> float:
    xs = [res.players[pid][f][0] for pid in res.players if pid[0] == team]
    if team == "H":  # defends x = 0: second-smallest x
        return sorted(xs)[1]
    return sorted(xs, reverse=True)[1]


def overlay_geom(o: dict, res: SceneResult, fa: int, fb: int, focus: str):
    """Static points or per-frame points (scene-local frames fa..fb-1)."""
    kind = o["kind"]
    if kind == "run_arrow":
        return {"static": res.paths.get(o["action"], [])}  # type: ignore[attr-defined]
    if kind == "pass_line":
        ev = next((e for e in res.events if e["id"] == o["event"]), None)
        return {"static": [_r(ev["p0"]), _r(ev["p1"])] if ev else []}
    if kind == "label":
        if "pitch" in o["anchor"]:
            return {"static": [_r(o["anchor"]["pitch"])]}
        pid = o["anchor"]["player"]
        return {"perFrame": [[_r((res.players[pid][f][0], res.players[pid][f][1] - 3.2))] for f in range(fa, fb)]}
    if kind in ("zone", "line"):
        g = o["geom"]
        if "rect" in g:
            x0, y0, x1, y1 = g["rect"]
            return {"static": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}
        if "named" in g:
            return {"static": named_rect(g["named"], "H" if focus == "both" else focus)}
        if "points" in g:
            return {"static": [_r(p) for p in g["points"]]}
        if "hull" in g:
            return {"perFrame": [[_r(p) for p in convex_hull([res.players[pid][f] for pid in g["hull"]])] for f in range(fa, fb)]}
        if "link" in g:
            a, b = g["link"]
            return {"perFrame": [[_r(res.players[a][f]), _r(res.players[b][f])] for f in range(fa, fb)]}
        team = g.get("def_line") or g.get("offside")
        return {"perFrame": [[[round(def_line_x(res, team, f), 2), 1.0], [round(def_line_x(res, team, f), 2), WIDTH - 1.0]]
                             for f in range(fa, fb)]}
    pids = o["players"]
    return {"perFrame": [[_r(res.players[pid][f]) for pid in pids] for f in range(fa, fb)]}


def build_doc(plan: dict, spec: dict, brief: dict, project_id: str, inputs: dict) -> dict:
    comp = compile_plan(plan, spec)
    aspect = brief["aspect"]
    focus = spec["focus_team"]
    scenes_out, events, actions, possession, overlays, cam_keys = [], [], [], [], [], []
    players = {pid: [] for pid in comp["scenes"][0].players}
    ball: list[int] = []
    camera: list[int] = []
    errors, warnings = list(comp["errors"]), list(comp["warnings"])
    prev_rect = None
    F0 = 0
    for res in comp["scenes"]:
        sc = res.plan
        tau0 = F0 * DT
        L = res.n * DT
        scenes_out.append({"id": res.id, "kind": res.kind, "tau0": round(tau0, 4), "len": round(L, 4),
                           "transition": sc["transition"],
                           "holds": [dict(h, tau=round(tau0 + h["tau"], 4)) for h in res.holds],
                           **({"reveals": [{"id": r["id"], "tau": round(tau0 + r["tau"], 4)} for r in res.reveals]}
                              if res.kind == "graphic" else {})})
        for pid in players:
            for f in range(res.n):
                x, y = res.players[pid][f]
                players[pid] += [round(x * 100), round(y * 100)]
        for f in range(res.n):
            bx, by, bz = res.ball[f]
            ball += [round(bx * 100), round(by * 100), round(bz * 100)]
        for e in res.events:
            events.append(dict({k: (_r(v) if k in ("p0", "p1") else v) for k, v in e.items()},
                               id=f"{res.id}:{e['id']}", scene=res.id, tau0=round(tau0 + e["tau0"], 4),
                               tau1=round(tau0 + e["tau1"], 4)))
        for a in res.actions:
            actions.append(dict(a, tau0=round(tau0 + a["tau0"], 4), tau1=round(tau0 + a["tau1"], 4)))
        for p in res.possession:
            t1 = L if p["tau1"] is None else min(p["tau1"], L)
            if p["tau0"] > L:
                continue
            possession.append(dict(p, tau0=round(tau0 + p["tau0"], 4), tau1=round(tau0 + t1, 4),
                                   event=f"{res.id}:{p['event']}" if p["event"] else None))
        if res.kind == "pitch":
            hard = sc["transition"] in ("reset", "cut") or prev_rect is None
            rects, keys = C.scene_camera(res, aspect, prev_rect, hard)
            cam_keys += [dict(k, tau=round(tau0 + k["tau"], 4), scene=res.id) for k in keys]
            for o in sc.get("overlays", []):
                ti = eval_time(o["in"], res.times, L)
                to = L if o["out"] == "scene.end" else eval_time(o["out"], res.times, L)
                if ti is None or to is None:
                    errors.append({"rule": "CH-02", "scene": res.id, "message": f"overlay {o['id']} in/out never resolves"})
                    continue
                ti, to = min(max(ti, 0.0), L), min(max(to, 0.0), L)
                fa, fb = int(round(ti * FPS)), int(round(to * FPS))
                if fb <= fa:
                    errors.append({"rule": "CH-40", "scene": res.id, "message": f"overlay {o['id']} is never visible"})
                    continue
                overlays.append({"id": f"{res.id}:{o['id']}", "scene": res.id, "kind": o["kind"],
                                 "tau_in": round(tau0 + ti, 4), "tau_out": round(tau0 + to, 4),
                                 "frame_in": F0 + fa, "frame_out": F0 + fb,
                                 "label": o.get("text"), "style": STYLE[o["kind"]],
                                 "geom": overlay_geom(o, res, fa, fb, focus),
                                 "players": o.get("players", [])})
        else:
            rects = [prev_rect or C.full(aspect)] * res.n
        for r in rects:
            camera += [round(r[0] * 100), round(r[1] * 100), round(r[2] * 100)]
        prev_rect = rects[-1] if rects else prev_rect
        F0 += res.n
    return {
        "version": "1", "project_id": project_id, "inputs": inputs, "hz": FPS, "aspect": aspect,
        "scenes": scenes_out, "events": events, "actions": actions, "possession": possession,
        "tracks": {"unit": "cm", "n": F0, "players": players, "ball": ball},
        "overlays": overlays, "camera_keys": cam_keys, "camera_track": camera,
        "report": {"errors": errors, "warnings": warnings},
    }


def load_inputs(project_dir) -> tuple[dict, dict, dict, dict]:
    from tms import manifest
    names = ("scene_plan", "tactic_spec", "brief")
    docs = {n: jsonio.read_json(manifest.artifact_path(project_dir, n)) for n in names}
    hashes = {n: jsonio.sha256_file(manifest.artifact_path(project_dir, n)) for n in names}
    return docs["scene_plan"], docs["tactic_spec"], docs["brief"], hashes
