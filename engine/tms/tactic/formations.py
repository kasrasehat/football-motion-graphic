"""Formation templates and the shape solver (config/formations.yaml)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from tms import paths
from tms.tactic.geometry import LENGTH, WIDTH, Point, dist, parse_formation, to_abs, to_norm


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((paths.config_dir() / "formations.yaml").read_text(encoding="utf-8"))


def template_names() -> list[str]:
    return sorted(config()["templates"])


def template(name: str) -> dict:
    t = config()["templates"].get(name)
    if t is None:
        raise KeyError(f"unknown template {name!r}; available: {', '.join(template_names())}")
    return t


@dataclass(frozen=True)
class Block:
    line_x: float
    depth: float
    width: float
    ball_shift: float

    @classmethod
    def parse(cls, s: str) -> "Block":
        parts = [float(v) for v in s.split(",")]
        if len(parts) != 4:
            raise ValueError("block must be line_x,depth,width,ball_shift")
        return cls(*parts)

    def as_dict(self) -> dict:
        return {"line_x": self.line_x, "depth": self.depth, "width": self.width, "ball_shift": self.ball_shift}


ROLE_PRIORITY = ["GK", "LB", "RB", "LWB", "RWB", "LCB", "RCB", "CB", "ST", "CF", "LS", "RS", "LW", "RW", "LM", "RM",
                 "DM", "LDM", "RDM", "AM", "LAM", "RAM", "SS", "LCM", "RCM", "CM"]


def assign_numbers(roles: list[str]) -> list[int]:
    """Classic shirt numbers: roles claim numbers in a fixed priority order (defenders, strikers, wingers,
    then midfielders), each taking its first free preferred number; leftovers fill 2..11 in order."""
    prefs = config()["numbers"]
    taken: set[int] = {1}
    out: list[int] = [-1] * len(roles)
    order = sorted(range(len(roles)), key=lambda i: (ROLE_PRIORITY.index(roles[i]) if roles[i] in ROLE_PRIORITY else 99, i))
    for i in order:
        n = next((k for k in prefs.get(roles[i], []) if k not in taken), None)
        if n is not None:
            out[i] = n
            taken.add(n)
    free = [k for k in range(2, 12) if k not in taken]
    return [n if n != -1 else free.pop(0) for n in out]


def solve(template_name: str, block: Block, ball_norm: Point | None = None) -> list[dict]:
    """Outfield + GK positions in the team-normalized frame. Returns [{role, line, pos}], GK first."""
    t = template(template_name)
    cfg = config()
    shift = 0.0
    if ball_norm is not None:
        shift = block.ball_shift * cfg["lateral_shift_gain"] * (ball_norm[1] - WIDTH / 2)
    g = cfg["goalkeeper"]
    gk_x = min(max(block.line_x - g["gap"], g["x_min"]), g["x_max"])
    out = [{"role": "GK", "line": 0, "pos": (gk_x, WIDTH / 2 + g["follow_shift"] * shift)}]
    for p in t["players"]:
        x = block.line_x + p["u"] * block.depth
        y = WIDTH / 2 + (p["v"] - 0.5) * block.width + shift
        out.append({"role": p["role"], "line": p["line"], "pos": (min(max(x, 1.0), LENGTH - 1.0), min(max(y, 1.0), WIDTH - 1.0))})
    return out


def separate(players: dict[str, tuple[str, Point]], fixed: set[str] = frozenset()) -> dict[str, Point]:
    """Push apart players closer than the configured separation (absolute frame). players: id -> (team, abs_pos)."""
    sep = config()["separation"]
    pos = {pid: list(p) for pid, (_, p) in players.items()}
    team = {pid: t for pid, (t, _) in players.items()}
    ids = sorted(pos)
    for _ in range(sep["iterations"]):
        moved = False
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                need = sep["teammates_m"] if team[a] == team[b] else sep["opponents_m"]
                d = dist(tuple(pos[a]), tuple(pos[b]))
                if d >= need:
                    continue
                moved = True
                if d < 1e-6:
                    dx, dy = (0.0, 1.0)
                else:
                    dx, dy = (pos[b][0] - pos[a][0]) / d, (pos[b][1] - pos[a][1]) / d
                push = (need - d) / 2 + 0.05
                movers = [m for m in (a, b) if m not in fixed] or [b]
                for m in movers:
                    sgn = -1 if m == a else 1
                    k = push * (2 if len(movers) == 1 else 1)
                    pos[m][0] = min(max(pos[m][0] + sgn * dx * k, 1.0), LENGTH - 1.0)
                    pos[m][1] = min(max(pos[m][1] + sgn * dy * k, 1.0), WIDTH - 1.0)
        if not moved:
            break
    return {pid: (round(p[0], 1), round(p[1], 1)) for pid, p in pos.items()}


def formation_of(template_name: str) -> str:
    return template(template_name)["formation"]


def validate_templates() -> list[str]:
    """Internal consistency of every template (used by tests)."""
    problems = []
    for name in template_names():
        t = template(name)
        counts = parse_formation(t["formation"])
        if sum(counts) != 10 or len(t["players"]) != 10:
            problems.append(f"{name}: needs 10 outfield players matching the formation")
        for line, n in enumerate(counts, 1):
            got = [p for p in t["players"] if p["line"] == line]
            if len(got) != n:
                problems.append(f"{name}: line {line} has {len(got)} players, formation says {n}")
        nums = assign_numbers([p["role"] for p in t["players"]])
        if sorted(nums) != list(range(2, 12)):
            problems.append(f"{name}: shirt numbers not 2..11: {nums}")
    return problems


def to_absolute(team: str, norm: Point) -> Point:
    return to_abs(team, norm)


def to_normalized(team: str, absolute: Point) -> Point:
    return to_norm(team, absolute)
