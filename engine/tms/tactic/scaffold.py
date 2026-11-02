"""`tms tactic scaffold` — a schema-shaped tactic_spec with engine-solved positions for both teams.
The author then fills title/summary/principles/triggers/strengths/weaknesses/counters (scaffold leaves them
empty on purpose so validation fails until they are written) and may fine-tune individual positions."""
from __future__ import annotations

from tms.tactic import formations as F
from tms.tactic.geometry import to_abs, to_norm


def other(team: str) -> str:
    return "A" if team == "H" else "H"


def in_possession_team(phase: str, focus: str) -> str:
    base = "H" if focus == "both" else focus
    return base if phase in F.config()["in_possession_phases"] else other(base)


def scaffold(project_id: str, phase: str, focus: str, home: str, away: str, home_base: str | None = None,
             away_base: str | None = None, home_block: F.Block | None = None, away_block: F.Block | None = None,
             holder: str | None = None) -> dict:
    cfg = F.config()
    if phase not in cfg["phase_blocks"] and (home_block is None or away_block is None):
        raise ValueError(f"phase {phase!r} has no default blocks (set pieces): pass --home-block and --away-block")
    poss = in_possession_team(phase, focus)
    templates = {"H": home, "A": away}
    blocks = {}
    for team, explicit in (("H", home_block), ("A", away_block)):
        key = "in_possession" if team == poss else "out_of_possession"
        blocks[team] = explicit or F.Block(*cfg["phase_blocks"][phase][key])

    solved: dict[str, list[dict]] = {}
    solved[poss] = F.solve(templates[poss], blocks[poss])
    roles_p = [p["role"] for p in solved[poss][1:]]
    nums_p = [1] + F.assign_numbers(roles_p)
    ids_p = [f"{poss}{n}" for n in nums_p]
    if holder is None:
        prefs = cfg["default_holder"].get(phase, ["GK"])
        holder = next((ids_p[i] for r in prefs for i, p in enumerate(solved[poss]) if p["role"] == r), ids_p[0])
    if not holder.startswith(poss):
        raise ValueError(f"holder {holder} is not in the team in possession ({poss}) for phase {phase}")
    hidx = ids_p.index(holder)
    ball_abs = to_abs(poss, solved[poss][hidx]["pos"])
    dfd = other(poss)
    solved[dfd] = F.solve(templates[dfd], blocks[dfd], ball_norm=to_norm(dfd, ball_abs))
    nums_d = [1] + F.assign_numbers([p["role"] for p in solved[dfd][1:]])

    meta: dict[str, tuple[str, dict, int]] = {}
    for team, nums in ((poss, nums_p), (dfd, nums_d)):
        for p, n in zip(solved[team], nums):
            meta[f"{team}{n}"] = (team, p, n)
    separated = F.separate({pid: (team, to_abs(team, p["pos"])) for pid, (team, p, _) in meta.items()}, fixed={holder})

    teams = {}
    for team, base, tmpl in (("H", home_base, home), ("A", away_base, away)):
        players = []
        for pid, (t, p, n) in sorted(meta.items(), key=lambda kv: (kv[1][1]["line"], kv[1][1]["pos"][1])):
            if t != team:
                continue
            nx, ny = to_norm(team, separated[pid])
            players.append({"id": pid, "number": n, "name": None, "role": p["role"], "line": p["line"],
                            "pos": [round(nx, 1), round(ny, 1)]})
        teams[team] = {"formation_base": base or F.formation_of(tmpl), "formation_phase": F.formation_of(tmpl),
                       "shape": {"template": tmpl, "block": blocks[team].as_dict()}, "players": players}
    return {
        "version": "1", "project_id": project_id, "title": "", "summary": "", "focus_team": focus, "phase": phase,
        "frame": "team_normalized", "teams": teams, "ball": {"holder": holder},
        "principles": [], "triggers": [], "strengths": [], "weaknesses": [], "counters": [], "assumptions": [],
    }
