"""Static render_props for the tactic snapshot (the image shown at the `approve tactic` gate)."""
from __future__ import annotations

from pathlib import Path

from tms import jsonio, remotion, theme
from tms.choreo.camera import full
from tms.state.project import ProjectError
from tms.tactic.geometry import to_abs


def short_label(pid: str, name: str, limit: int = 28) -> str:
    """'P2 Eights live in the half-spaces' -> fits 28 chars, cut at a word boundary with an ellipsis."""
    text = f"{pid} {name}"
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def still_props(spec: dict, brief: dict, scale: float = 1.0) -> dict:
    res = theme.resolution(brief["aspect"], scale)
    players, entities, positions = {}, [], {}
    for t in "HA":
        for p in spec["teams"][t]["players"]:
            x, y = to_abs(t, tuple(p["pos"]))
            positions[p["id"]] = (x, y)
            players[p["id"]] = [round(x * 100), round(y * 100)]
            label = (p.get("name") or None) if brief.get("show_names") else None
            entities.append({"id": p["id"], "team": t, "number": p["number"], "label": label})
    hx, hy = positions[spec["ball"]["holder"]]
    overlays = []
    for i, pr in enumerate(spec["principles"]):
        pts = [list(positions[pid]) for pid in pr["players"]]
        overlays.append({"id": f"N{2 * i + 1:02d}", "kind": "ring", "from": 0, "to": 1,
                         "inAnim": {"anim": "none", "frames": 0}, "outAnim": {"anim": "none", "frames": 0},
                         "geom": {"static": pts}, "style": {"color": "accent", "dash": False, "fill": False}, "label": None})
        ax = sum(p[0] for p in pts) / len(pts)
        ay = min(p[1] for p in pts) - 3.5
        overlays.append({"id": f"N{2 * i + 2:02d}", "kind": "label", "from": 0, "to": 1,
                         "inAnim": {"anim": "none", "frames": 0}, "outAnim": {"anim": "none", "frames": 0},
                         "geom": {"static": [[round(ax, 2), round(max(ay, 2.0), 2)]]},
                         "style": {"color": "ink", "dash": False, "fill": True}, "label": short_label(pr['id'], pr['name'])})
    return {
        "version": "1", "project_id": spec["project_id"], "inputs": {},
        "fps": 30, "width": res["width"], "height": res["height"], "durationInFrames": 1,
        "orientation": res["orientation"], "theme": theme.render_theme(brief), "entities": entities,
        "tracks": {"unit": "cm", "players": players, "ball": [round((hx + 0.9) * 100), round(hy * 100), 11]},
        "camera": [round(v * 100) for v in full(brief["aspect"])], "pitchVisible": [[0, 1]], "freeze": [],
        "scenes": [{"id": "S01", "kind": "pitch", "from": 0, "to": 1, "title": spec["title"][:28] or "Tactic"}],
        "overlays": overlays, "graphics": [], "captions": [], "titleCard": None, "endCard": None,
        "debug": {"overlay": False},
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
