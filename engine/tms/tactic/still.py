"""Static render_props for the tactic snapshot (the image shown at the `approve tactic` / `approve analysis` gates).

The frame is split between the pitch and a key panel (`principleRail`) that holds the whole principle titles, so
nothing written about the tactic can land on a player. The renderer solves the name labels around tokens and ball.
"""
from __future__ import annotations

import math
from pathlib import Path

from tms import jsonio, remotion, theme
from tms.render.projection import ball_radius_px, px_per_metre, resolution_factor, ring_outer_radius_px, token_radius_px
from tms.state.project import ProjectError
from tms.tactic.geometry import LENGTH, WIDTH, dist, to_abs

# Panel thickness at 1080p: its width in landscape (pitch beside it), its height otherwise (pitch above it).
RAIL_PX_1080 = {"landscape": 330.0, "portrait": 430.0, "square": 340.0}
RAIL_MARGIN_PX_1080 = 16.0
PITCH_MARGIN_M = 3.0  # run-off kept in view around the pitch; the goals stand 2 m behind the line
ENTITY_LABEL_MAX = 18  # render_props entities[].label


def name_label(name: str | None) -> str | None:
    """A player name that fits the token pill: whole if it can be, else the longest run of trailing words (surname)."""
    if not name:
        return None
    if len(name) <= ENTITY_LABEL_MAX:
        return name
    words = name.split()
    tail = ""
    for word in reversed(words):
        joined = f"{word} {tail}".strip()
        if len(joined) > ENTITY_LABEL_MAX:
            break
        tail = joined
    return tail or name[: ENTITY_LABEL_MAX - 1] + "…"


def still_frame(width: int, height: int, orientation: str) -> tuple[tuple[float, float, float], list[float]]:
    """(camera (cx, cy, w) in metres, panel rect [x0, y0, x1, y1] in px): the whole pitch in the part left free."""
    u = resolution_factor(width, height)
    rail = RAIL_PX_1080[orientation] * u
    m = RAIL_MARGIN_PX_1080 * u
    free_w, free_h = (width - rail, height) if orientation == "landscape" else (width, height - rail)
    along, across = (free_h, free_w) if orientation == "portrait" else (free_w, free_h)
    s = min(along / (LENGTH + 2 * PITCH_MARGIN_M), across / (WIDTH + 2 * PITCH_MARGIN_M))
    if orientation == "landscape":
        return (LENGTH / 2 + rail / (2 * s), WIDTH / 2, width / s), [free_w, m, width - m, height - m]
    if orientation == "portrait":
        return (LENGTH / 2 - rail / (2 * s), WIDTH / 2, height / s), [m, free_h, width - m, height - m]
    return (LENGTH / 2, WIDTH / 2 + rail / (2 * s), width / s), [m, free_h, width - m, height - m]


def _ball_spot(holder: tuple[float, float], team: str, others: list[tuple[float, float]], ringed: bool,
               camera: tuple[float, float, float], res: dict) -> tuple[float, float]:
    """Where the ball sits at the holder's feet: fully outside their token and ring (those are drawn over the ball),
    clear of every other player. Tried in the attacking direction first, then behind (the labels prefer above and
    below the token), then the diagonals, then straight out to the sides."""
    width, height, orientation = res["width"], res["height"], res["orientation"]
    s = px_per_metre(camera[2], width, height, orientation)
    u = resolution_factor(width, height)
    r = token_radius_px(camera[2], width, height, orientation)
    ball_r = ball_radius_px(s, u)
    ring = ring_outer_radius_px(r, u)
    reach = ((ring if ringed else r) + ball_r + 2 * u) / s
    keep = (ring + ball_r + 2 * u) / s
    fwd = 1.0 if team == "H" else -1.0
    diag = math.sqrt(0.5)
    best, best_clear = None, -1.0
    for dx, dy in ((fwd, 0.0), (-fwd, 0.0), (fwd * diag, diag), (fwd * diag, -diag), (-fwd * diag, diag),
                   (-fwd * diag, -diag), (0.0, 1.0), (0.0, -1.0)):
        spot = (holder[0] + dx * reach, holder[1] + dy * reach)
        if not (0.0 <= spot[0] <= LENGTH and 0.0 <= spot[1] <= WIDTH):
            continue
        clear = min((dist(spot, o) for o in others), default=math.inf)
        if clear >= keep:
            return spot
        if clear > best_clear:
            best, best_clear = spot, clear
    return best if best is not None else holder


def still_props(spec: dict, brief: dict, scale: float = 1.0) -> dict:
    res = theme.resolution(brief["aspect"], scale)
    camera, rail_rect = still_frame(res["width"], res["height"], res["orientation"])
    players, entities, positions, info = {}, [], {}, {}
    for t in "HA":
        for p in spec["teams"][t]["players"]:
            x, y = to_abs(t, tuple(p["pos"]))
            positions[p["id"]] = (x, y)
            info[p["id"]] = {"team": t, "number": p["number"], "name": p.get("name")}
            players[p["id"]] = [round(x * 100), round(y * 100)]
            label = name_label(p.get("name")) if brief.get("show_names") else None
            entities.append({"id": p["id"], "team": t, "number": p["number"], "label": label})
    ringed = list(dict.fromkeys(pid for pr in spec["principles"] for pid in pr["players"]))
    overlays = [{"id": "N01", "kind": "ring", "from": 0, "to": 1,
                 "inAnim": {"anim": "none", "frames": 0}, "outAnim": {"anim": "none", "frames": 0},
                 "geom": {"static": [[round(v, 2) for v in positions[pid]] for pid in ringed]},
                 "style": {"color": "accent", "dash": False, "fill": False}, "label": None}]
    holder = spec["ball"]["holder"]
    bx, by = _ball_spot(positions[holder], info[holder]["team"], [q for pid, q in positions.items() if pid != holder],
                        holder in ringed, camera, res)
    rail = {
        "rect": [round(v, 1) for v in rail_rect],
        "title": spec["title"],
        "ball": {"team": info[holder]["team"], "number": info[holder]["number"],
                 "name": info[holder]["name"] if brief.get("show_names") else None},
        "principles": [{"id": pr["id"], "name": pr["name"],
                        "players": [{"team": info[pid]["team"], "number": info[pid]["number"]}
                                    for t in "HA" for pid in pr["players"] if info[pid]["team"] == t]}
                       for pr in spec["principles"]],
    }
    return {
        "version": "1", "project_id": spec["project_id"], "inputs": {},
        "fps": 30, "width": res["width"], "height": res["height"], "durationInFrames": 1,
        "orientation": res["orientation"], "theme": theme.render_theme({**brief, "show_crests": False}), "entities": entities,  # the still draws no crests
        "tracks": {"unit": "cm", "players": players, "ball": [round(bx * 100), round(by * 100), 11]},
        "camera": [round(v * 100) for v in camera], "pitchVisible": [[0, 1]], "freeze": [],
        "scenes": [{"id": "S01", "kind": "pitch", "from": 0, "to": 1, "title": ""}],  # the panel carries the title
        "overlays": overlays, "graphics": [], "captions": [], "titleCard": None, "endCard": None,
        "principleRail": rail, "debug": {"overlay": False},
    }


def render_still(project_dir: Path, out: Path | None = None) -> Path:
    missing = [n for n in ("tactic_spec", "brief") if not (project_dir / "artifacts" / f"{n}.json").is_file()]
    if missing:
        raise ProjectError(f"project {project_dir.name} has no {' or '.join(missing)} yet, so there is no tactic still "
                           "to render. If this is the wrong project, pass --project <slug>.")
    spec = jsonio.read_json(project_dir / "artifacts" / "tactic_spec.json")
    brief = jsonio.read_json(project_dir / "artifacts" / "brief.json")
    props = still_props(spec, brief)
    props_file = project_dir / "renders" / "tactic_still.props.json"
    jsonio.write_json(props_file, props, compact=True)
    out = out or project_dir / "renders" / "tactic_still.png"
    remotion.render("TacticVideo", out, props=props_file, still=0, timeout=600)
    return out
