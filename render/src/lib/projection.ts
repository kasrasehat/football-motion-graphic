// World (pitch metres) -> screen (px) projection. Mirrors engine/tms/render/projection.py exactly;
// both are checked against tests/fixtures/projection_vectors.json (<= 1e-6 px).
//
// Pitch frame: 105 x 68 m, origin top-left, +x right (home attacks +x), +y down.
// Camera: (cx, cy, w) in metres; w = visible extent along pitch x.
//   landscape / square: pitch x -> screen right, pitch y -> screen down;   s = width / w
//   portrait:           pitch x -> screen UP (home attacks up), pitch y -> screen right;  s = height / w
// It is a similarity transform (uniform scale + 0 / 90 degree rotation), so circles stay circles.

export type Orientation = "landscape" | "portrait" | "square";

export interface Camera {
  cx: number;
  cy: number;
  w: number;
}

export const PITCH_LENGTH_M = 105;
export const PITCH_WIDTH_M = 68;
/** Physical token diameter (metres) and its floor in px at 1080p (scaled by min(width,height)/1080). */
export const TOKEN_DIAMETER_M = 2.0;
export const TOKEN_MIN_DIAMETER_PX_1080 = 26;
/** Ball size on the ground: exaggerated (a real ball is 0.22 m) so it reads at full-pitch zoom. */
export const BALL_DIAMETER_M = 0.7;
export const BALL_MIN_R_PX_1080 = 8;

/** Pixels per metre for this camera / output. */
export function pxPerMetre(w: number, width: number, height: number, orientation: Orientation): number {
  return orientation === "portrait" ? height / w : width / w;
}

/** Resolution factor relative to 1080p (1.0 for 1920x1080, 1080x1920, 1080x1080; 0.5 for the half sizes). */
export function resolutionFactor(width: number, height: number): number {
  return Math.min(width, height) / 1080;
}

export function worldToScreen(
  x: number,
  y: number,
  cam: Camera,
  width: number,
  height: number,
  orientation: Orientation,
): [number, number] {
  const s = pxPerMetre(cam.w, width, height, orientation);
  if (orientation === "portrait") {
    return [width / 2 + (y - cam.cy) * s, height / 2 - (x - cam.cx) * s];
  }
  return [width / 2 + (x - cam.cx) * s, height / 2 + (y - cam.cy) * s];
}

export function screenToWorld(
  sx: number,
  sy: number,
  cam: Camera,
  width: number,
  height: number,
  orientation: Orientation,
): [number, number] {
  const s = pxPerMetre(cam.w, width, height, orientation);
  if (orientation === "portrait") {
    return [cam.cx - (sy - height / 2) / s, cam.cy + (sx - width / 2) / s];
  }
  return [cam.cx + (sx - width / 2) / s, cam.cy + (sy - height / 2) / s];
}

/** SVG `matrix(a b c d e f)` mapping world metres to screen px: x' = a*x + c*y + e, y' = b*x + d*y + f. */
export function worldMatrix(
  cam: Camera,
  width: number,
  height: number,
  orientation: Orientation,
): [number, number, number, number, number, number] {
  const s = pxPerMetre(cam.w, width, height, orientation);
  if (orientation === "portrait") {
    return [0, -s, s, 0, width / 2 - cam.cy * s, height / 2 + cam.cx * s];
  }
  return [s, 0, 0, s, width / 2 - cam.cx * s, height / 2 - cam.cy * s];
}

/** Screen angle (radians, SVG convention: 0 = +x screen, positive = clockwise) of the world direction (dx, dy). */
export function screenAngle(dx: number, dy: number, orientation: Orientation): number {
  return orientation === "portrait" ? Math.atan2(-dx, dy) : Math.atan2(dy, dx);
}

/** Player token radius in px: physical 2.0 m diameter, never below 26 px diameter at 1080p. */
export function tokenRadiusPx(w: number, width: number, height: number, orientation: Orientation): number {
  const s = pxPerMetre(w, width, height, orientation);
  return Math.max((TOKEN_DIAMETER_M / 2) * s, (TOKEN_MIN_DIAMETER_PX_1080 / 2) * resolutionFactor(width, height));
}

/** Ball radius in px on the ground (`s` px per metre, `u` 1080p size factor). Twin of ball_radius_px in projection.py. */
export function ballRadiusPx(s: number, u: number): number {
  return Math.max((BALL_DIAMETER_M / 2) * s, BALL_MIN_R_PX_1080 * u);
}
