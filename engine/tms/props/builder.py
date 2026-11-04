"""Build render_props. Every output frame g maps to a fractional tau-frame through the timeline warp; tracks,
camera and per-frame overlay geometry are sampled there (linear interpolation, so slow-downs stay smooth)."""
from __future__ import annotations

from tms import theme
from tms.timeline import FPS, tau_at, wrap

ANIM = {
    "run_arrow": ({"anim": "draw", "frames": 12}, {"anim": "fade", "frames": 8}),
    "pass_line": ({"anim": "draw", "frames": 8}, {"anim": "fade", "frames": 8}),
    "zone": ({"anim": "fade", "frames": 10}, {"anim": "fade", "frames": 8}),
    "line": ({"anim": "fade", "frames": 8}, {"anim": "fade", "frames": 8}),
    "ring": ({"anim": "pop", "frames": 8}, {"anim": "fade", "frames": 6}),
    "spotlight": ({"anim": "fade", "frames": 10}, {"anim": "fade", "frames": 8}),
    "label": ({"anim": "fade", "frames": 8}, {"anim": "fade", "frames": 6}),
    "distance": ({"anim": "draw", "frames": 10}, {"anim": "fade", "frames": 6}),
    "polygon": ({"anim": "draw", "frames": 12}, {"anim": "fade", "frames": 8}),
}


def frame_map(choreo: dict, tl: dict) -> list[float]:
    """Output frame -> global tau-frame (float)."""
    n_tau = choreo["tracks"]["n"]
    start = {s["id"]: s for s in choreo["scenes"]}
    out = [0.0] * tl["frames"]
    for s in tl["scenes"]:
        cs = start[s["id"]]
        base = cs["tau0"] * FPS
        for g in range(s["from"], s["to"]):
            out[g] = min(base + tau_at(s["warp"], g - s["from"]) * FPS, n_tau - 1)
    first = tl["scenes"][0]["from"]
    last_to = tl["scenes"][-1]["to"]
    for g in range(0, first):
        out[g] = 0.0
    for g in range(last_to, tl["frames"]):
        out[g] = float(n_tau - 1)
    return out


def _lerp_flat(arr: list[int], stride: int, k: int, x: float) -> int:
    i = int(x)
    j = min(i + 1, len(arr) // stride - 1)
    u = x - i
    a, b = arr[i * stride + k], arr[j * stride + k]
    return int(round(a + (b - a) * u))


def resolve_ref(ref: str, dossier: dict | None, prediction: dict | None):
    """text:literal | prediction.path | dossier fact key -> value (None when it does not resolve)."""
    if ref.startswith("text:"):
        return ref[5:]
    if ref.startswith("prediction."):
        cur = prediction
        for part in ref.split(".")[1:]:
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur
    if dossier and ref in dossier["facts"]:
        return dossier["facts"][ref]["value"]
    return None


def _spec_lineup(players, team: dict | None):
    """Copies of `players` with their line and team-normalized y from the tactic spec, matched by shirt number.
    `players` itself unless every one has exactly one match; the board then keeps its position-based rows."""
    if not team or not isinstance(players, list):
        return players
    by_number = {p["number"]: p for p in team["players"]}
    numbers = [p.get("number") if isinstance(p, dict) else None for p in players]
    if (len(by_number) != len(team["players"]) or not all(isinstance(n, int) and n in by_number for n in numbers)
            or len(set(numbers)) != len(numbers)):
        return players
    return [{**p, "line": by_number[n]["line"], "y": by_number[n]["pos"][1]} for p, n in zip(players, numbers)]


def _graphic_data(scene: dict, dossier: dict | None, prediction: dict | None, analysis: dict | None = None,
                  spec: dict | None = None) -> dict:
    """Resolve a graphic scene's bind slots into the template data contract (see skills/stage-storyboard)."""
    data = {}
    for slot, ref in scene["bind"].items():
        if isinstance(ref, list):
            vals = [resolve_ref(r, dossier, prediction) for r in ref if not r.startswith("KB")]
            if scene["template"] == "team_news" and all(isinstance(v, list) for v in vals):
                vals = [x for v in vals for x in v]  # injuries + suspensions in one column
            data[slot] = vals
        elif ref.startswith("KB") and analysis and spec:
            kb = next((k for k in analysis["key_battles"] if k["id"] == ref), None)
            names = {p["id"]: p for t in "HA" for p in spec["teams"][t]["players"]}
            if kb:
                hp, ap = names.get(kb["home_player"], {}), names.get(kb["away_player"], {})
                data.update(title=kb["title"], why=kb["why"],
                            home_player={"name": hp.get("name") or kb["home_player"], "number": hp.get("number")},
                            away_player={"name": ap.get("name") or kb["away_player"], "number": ap.get("number")})
        else:
            data[slot] = resolve_ref(ref, dossier, prediction)
    if scene["template"] == "key_player_duel":
        data.setdefault("home_stats", [])
        data.setdefault("away_stats", [])
        for side in ("home_stats", "away_stats"):  # stat slots are bound as alternating [label, value, ...] lists
            if data[side] and not isinstance(data[side][0], dict):
                it = data[side]
                data[side] = [{"label": str(it[i]), "value": it[i + 1]} for i in range(0, len(it) - 1, 2)]
    if scene["template"] == "lineup_board":
        teams = (spec or {}).get("teams", {})
        for slot, side in (("home", "H"), ("away", "A")):
            if slot in data:
                data[slot] = _spec_lineup(data[slot], teams.get(side))
    return data


def _overlay_style(o: dict, plan_scene: dict) -> dict:
    """A run arrow takes the running player's team colour (the action handle starts with the player id)."""
    if o["kind"] != "run_arrow":
        return o["style"]
    src = next((x for x in plan_scene.get("overlays", []) if f"{plan_scene['id']}:{x['id']}" == o["id"]), {})
    team = src.get("action", "")[:1]
    return {**o["style"], "color": team} if team in ("H", "A") else o["style"]


def build(choreo: dict, tl: dict, brief: dict, narration: dict, plan: dict, spec: dict, *, scale: float = 1.0,
          dossier: dict | None = None, prediction: dict | None = None, inputs: dict | None = None,
          analysis: dict | None = None) -> dict:
    res = theme.resolution(brief["aspect"], scale)
    fm = frame_map(choreo, tl)
    N = tl["frames"]
    tracks = {}
    for pid, arr in choreo["tracks"]["players"].items():
        flat = []
        for g in range(N):
            flat += [_lerp_flat(arr, 2, 0, fm[g]), _lerp_flat(arr, 2, 1, fm[g])]
        tracks[pid] = flat
    ball, cam = [], []
    for g in range(N):
        ball += [_lerp_flat(choreo["tracks"]["ball"], 3, k, fm[g]) for k in range(3)]
        cam += [_lerp_flat(choreo["camera_track"], 3, k, fm[g]) for k in range(3)]

    kinds = {s["id"]: s["kind"] for s in choreo["scenes"]}
    tl_scenes = {s["id"]: s for s in tl["scenes"]}
    plan_scenes = {s["id"]: s for s in plan["scenes"]}
    pitch_visible, scenes, graphics, freeze = [], [], [], []
    for s in tl["scenes"]:
        kind = kinds[s["id"]]
        scenes.append({"id": s["id"], "kind": kind, "from": s["from"], "to": s["to"], "title": plan_scenes[s["id"]]["title"][:28]})
        if kind == "pitch":
            pitch_visible.append([s["from"], s["to"]])
        else:
            ps = plan_scenes[s["id"]]
            reveals = []
            for r in ps.get("reveals", []):
                off = 0
                for (t0, f0), (t1, f1) in zip(s["warp"], s["warp"][1:]):
                    if t0 <= r["at"] <= t1 and t1 > t0:
                        off = f0 + (f1 - f0) * (r["at"] - t0) / (t1 - t0)
                        break
                reveals.append({"id": r["id"], "frame": s["from"] + int(round(off))})
            graphics.append({"id": s["id"], "template": ps["template"], "from": s["from"], "to": s["to"],
                             "data": _graphic_data(ps, dossier, prediction, analysis, spec), "reveals": reveals})
        freeze += _freeze_spans(s, kind)
    # pitch also visible under the title and end cards
    intro, outro = tl["intro"], tl["outro"]
    if intro["to"] > intro["from"]:
        pitch_visible.insert(0, [intro["from"], intro["to"]])
    if outro["to"] > outro["from"] and kinds[tl["scenes"][-1]["id"]] == "pitch":
        pitch_visible.append([outro["from"], outro["to"]])
    pitch_visible = _merge(pitch_visible)

    overlays = []
    for o in choreo["overlays"]:
        gs = [g for g in range(N) if o["frame_in"] <= fm[g] < o["frame_out"] and _in_scene(g, tl_scenes[o["scene"]])]
        if not gs:
            continue
        a, b = gs[0], gs[-1] + 1
        if "static" in o["geom"]:
            geom = {"static": o["geom"]["static"]}
        else:
            pf = o["geom"]["perFrame"]
            geom = {"perFrame": [pf[min(max(int(round(fm[g])) - o["frame_in"], 0), len(pf) - 1)] for g in range(a, b)]}
        ina, outa = ANIM[o["kind"]]
        overlays.append({"id": o["id"], "kind": o["kind"], "from": a, "to": b, "inAnim": ina, "outAnim": outa,
                         "geom": geom, "style": _overlay_style(o, plan_scenes[o["scene"]]), "label": o.get("label")})

    words = {w["i"]: w for w in tl["words"]}
    captions = []
    if brief.get("captions", True):
        for c in tl["captions"]:
            ws = [words[i] for i in range(c["words"][0], c["words"][1] + 1) if i in words]
            lines = wrap([w["display"] for w in ws], 42)
            line_of = {k: li for li, idxs in enumerate(lines) for k in idxs}
            captions.append({"from": c["from"], "to": c["to"], "lines": c["lines"],
                             "words": [{"t": w["display"], "from": w["from"], "to": w["to"], "line": min(line_of[k], 1)} for k, w in enumerate(ws)],
                             "place": c["place"]})
    info = {p["id"]: p for t in "HA" for p in spec["teams"][t]["players"]}
    entities = []
    for t in ("H", "A"):
        for pid in sorted((e for e in choreo["tracks"]["players"] if e[0] == t), key=lambda e: int(e[1:])):
            name = info[pid].get("name") if brief.get("show_names") else None
            entities.append({"id": pid, "team": t, "number": info[pid]["number"], "label": name[:18] if name else None})
    return {
        "version": "1", "project_id": choreo["project_id"], "inputs": inputs or {},
        "fps": FPS, "width": res["width"], "height": res["height"], "durationInFrames": N, "orientation": res["orientation"],
        "theme": theme.render_theme(brief), "entities": entities,
        "tracks": {"unit": "cm", "players": tracks, "ball": ball}, "camera": cam,
        "pitchVisible": pitch_visible, "freeze": freeze, "scenes": scenes, "overlays": overlays, "graphics": graphics,
        "captions": captions,
        "titleCard": {"from": intro["from"], "to": intro["to"], "title": narration["title_card"]["title"],
                      "subtitle": narration["title_card"]["subtitle"]} if intro["to"] > intro["from"] else None,
        "endCard": {"from": outro["from"], "to": outro["to"], "text": narration["end_card"]["text"]} if outro["to"] > outro["from"] else None,
        "debug": {"overlay": False},
    }


def _in_scene(g: int, s: dict) -> bool:
    return s["from"] <= g < s["to"]


def _freeze_spans(s: dict, kind: str) -> list[list[int]]:
    """Spans for the "paused" treatment: real pauses on the pitch only. A beat under a second isn't one, and a card has nothing to pause."""
    if kind != "pitch":
        return []
    return [[s["from"] + int(f0), s["from"] + int(f1)]
            for (t0, f0), (t1, f1) in zip(s["warp"], s["warp"][1:]) if t1 == t0 and f1 - f0 >= FPS]


def _merge(spans):
    spans = sorted(spans)
    out = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out

