"""Pitch geometry (metres). Absolute frame: origin top-left, +x right, +y down, home (H) attacks +x.
Team-normalized frame: every team attacks +x; away -> absolute is a 180-degree rotation, NOT a mirror
(a mirror would swap the away team's left and right)."""
from __future__ import annotations

import math
import re

LENGTH, WIDTH = 105.0, 68.0
CENTER = (LENGTH / 2, WIDTH / 2)
GOAL_HALF = 7.32 / 2
PENALTY_DEPTH, PENALTY_HALF = 16.5, 40.32 / 2

Point = tuple[float, float]


def to_abs(team: str, p: Point) -> Point:
    return (p[0], p[1]) if team == "H" else (LENGTH - p[0], WIDTH - p[1])


def to_norm(team: str, p: Point) -> Point:
    return to_abs(team, p)  # the rotation is its own inverse


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def in_bounds(p: Point, margin: float = 0.0) -> bool:
    return -margin <= p[0] <= LENGTH + margin and -margin <= p[1] <= WIDTH + margin


def side_of_role(role: str) -> str:
    """'L', 'R' or 'C' from the role code (LCB -> L, RW -> R, DM -> C)."""
    if role.startswith("L"):
        return "L"
    if role.startswith("R"):
        return "R"
    return "C"


def parse_formation(f: str) -> list[int]:
    if not re.fullmatch(r"[1-9](-[1-9]){1,4}", f):
        raise ValueError(f"bad formation {f!r}")
    return [int(d) for d in f.split("-")]


# Named zones (team-normalized frame of the team they are used for: the team attacks +x).
# Each value is the zone centre; used as move targets ({"zone": name}).
ZONES: dict[str, Point] = {}
_THIRDS = {"def": 17.5, "mid": 52.5, "att": 87.5}
_CHANNELS = {"l_wide": 6.0, "l_half_space": 20.0, "centre": 34.0, "r_half_space": 48.0, "r_wide": 62.0}
for _ch, _y in _CHANNELS.items():
    for _th, _x in _THIRDS.items():
        ZONES[f"{_ch}_{_th}"] = (_x, _y)
ZONES.update({
    "zone14": (80.0, 34.0),
    "box": (96.0, 34.0),
    "six_yard": (101.0, 34.0),
    "penalty_spot": (94.0, 34.0),
    "near_post": (102.0, 30.0),
    "far_post": (102.0, 38.0),
    "own_box": (9.0, 34.0),
    "centre_circle": (52.5, 34.0),
})


def zone_point(name: str) -> Point:
    if name not in ZONES:
        raise KeyError(f"unknown zone {name!r}; known: {', '.join(sorted(ZONES))}")
    return ZONES[name]


def defensive_line_x(xs: list[float]) -> float:
    """Second-last defender line for a team defending the goal at x=105 (absolute, attackers moving +x)."""
    s = sorted(xs, reverse=True)
    return s[1] if len(s) > 1 else s[0]
