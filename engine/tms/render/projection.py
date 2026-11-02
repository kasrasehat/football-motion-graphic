"""World (pitch metres) -> screen (px) projection used by the Remotion renderer.

This is the Python twin of ``render/src/lib/projection.ts``. Both are checked against the shared vectors in
``tests/fixtures/projection_vectors.json`` (agreement <= 1e-6 px), so pixel probes computed here land exactly where
the renderer draws. Pure functions, no dependencies.

Pitch frame: 105 x 68 m, origin top-left, +x right (home attacks +x), +y down.
Camera: (cx, cy, w) in metres; w = visible extent along pitch x.
  landscape / square: pitch x -> screen right, pitch y -> screen down;           s = width / w
  portrait:           pitch x -> screen UP (home attacks up), y -> screen right;  s = height / w
"""
from __future__ import annotations

from typing import Any, Literal, Sequence

Orientation = Literal["landscape", "portrait", "square"]

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
TOKEN_DIAMETER_M = 2.0
TOKEN_MIN_DIAMETER_PX_1080 = 26.0


def px_per_metre(w: float, width: int, height: int, orientation: str) -> float:
    """Pixels per metre for this camera width (metres along pitch x) and output size."""
    return height / w if orientation == "portrait" else width / w


def resolution_factor(width: int, height: int) -> float:
    """1.0 at 1080p-class outputs (1920x1080, 1080x1920, 1080x1080), 0.5 at the half sizes."""
    return min(width, height) / 1080


def world_to_screen(x: float, y: float, camera: Sequence[float], width: int, height: int,
                    orientation: str) -> tuple[float, float]:
    """Project a pitch point (metres) to screen px for camera (cx, cy, w) in metres."""
    cx, cy, w = camera
    s = px_per_metre(w, width, height, orientation)
    if orientation == "portrait":
        return width / 2 + (y - cy) * s, height / 2 - (x - cx) * s
    return width / 2 + (x - cx) * s, height / 2 + (y - cy) * s


def screen_to_world(sx: float, sy: float, camera: Sequence[float], width: int, height: int,
                    orientation: str) -> tuple[float, float]:
    """Inverse of :func:`world_to_screen`."""
    cx, cy, w = camera
    s = px_per_metre(w, width, height, orientation)
    if orientation == "portrait":
        return cx - (sy - height / 2) / s, cy + (sx - width / 2) / s
    return cx + (sx - width / 2) / s, cy + (sy - height / 2) / s


def token_radius_px(w: float, width: int, height: int, orientation: str) -> float:
    """Player token radius in px: physical 2.0 m diameter, never below 26 px diameter at 1080p."""
    s = px_per_metre(w, width, height, orientation)
    return max(TOKEN_DIAMETER_M / 2 * s, TOKEN_MIN_DIAMETER_PX_1080 / 2 * resolution_factor(width, height))


# --- render_props helpers (frame-indexed, centimetres -> metres) -------------------------------------------------

def _clamp_frame(frame: int, n: int) -> int:
    return max(0, min(int(frame), n - 1))


def camera_at(props: dict[str, Any], frame: int) -> tuple[float, float, float]:
    """Camera (cx, cy, w) in metres at ``frame``."""
    cam = props["camera"]
    i = _clamp_frame(frame, len(cam) // 3) * 3
    return cam[i] / 100, cam[i + 1] / 100, cam[i + 2] / 100


def player_at(props: dict[str, Any], pid: str, frame: int) -> tuple[float, float]:
    """Player position (metres) at ``frame``."""
    tr = props["tracks"]["players"][pid]
    i = _clamp_frame(frame, len(tr) // 2) * 2
    return tr[i] / 100, tr[i + 1] / 100


def ball_at(props: dict[str, Any], frame: int) -> tuple[float, float, float]:
    """Ball (x, y, z) in metres at ``frame``."""
    b = props["tracks"]["ball"]
    i = _clamp_frame(frame, len(b) // 3) * 3
    return b[i] / 100, b[i + 1] / 100, b[i + 2] / 100


def project_player(props: dict[str, Any], pid: str, frame: int, scale: float = 1.0) -> tuple[float, float]:
    """Screen px of a player's token centre in a render of ``props`` at output ``scale``."""
    x, y = player_at(props, pid, frame)
    sx, sy = world_to_screen(x, y, camera_at(props, frame), props["width"], props["height"], props["orientation"])
    return sx * scale, sy * scale


def project_ball(props: dict[str, Any], frame: int, scale: float = 1.0) -> tuple[float, float]:
    """Screen px of the ball centre (ground position; the renderer draws the ball at its ground point)."""
    x, y, _z = ball_at(props, frame)
    sx, sy = world_to_screen(x, y, camera_at(props, frame), props["width"], props["height"], props["orientation"])
    return sx * scale, sy * scale
