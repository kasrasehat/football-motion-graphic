// Deterministic placement of overlay labels so they do not cover player tokens.
// A slot is chosen once per overlay over its whole [from, to) window (never per frame), so labels never jump.
import type { Overlay, RenderProps } from "../generated/render_props";
import { catmullRom, clipPolygonToRect, pointAt, polyLength, type P2 } from "./geometry";
import { hudRects } from "./hud";
import { safeArea, unit } from "./layout";
import { overlayPoints } from "./overlays";
import { tokenRadiusPx, worldToScreen } from "./projection";
import { cameraAt, playerAt } from "./tracks";

export type UV = [number, number];

function inside(poly: P2[], x: number, y: number): boolean {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]!;
    const [xj, yj] = poly[j]!;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

function bbox(poly: P2[]): [number, number, number, number] {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const [x, y] of poly) {
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return [x0, y0, x1, y1];
}

/**
 * Index of the candidate slot whose label box (boxW x boxH px, centred on `anchor(frame, i)`) overlaps the fewest
 * player tokens and HUD boxes (captions, lower-third, pause badge) over the overlay's window; then the fewest frames
 * pushed outside the safe area; then the lowest `pref(i)` (+ any per-frame `extra(frame, i)` penalty).
 */
export function chooseSlot(
  p: RenderProps,
  o: { from: number; to: number },
  n: number,
  anchor: (frame: number, i: number) => P2 | null,
  boxW: number,
  boxH: number,
  pref: (i: number) => number,
  extra?: (frame: number, i: number) => number,
): number {
  const safe = safeArea(p.width, p.height);
  const hud = new Map<number, ReturnType<typeof hudRects>>();
  const step = Math.max(1, Math.floor((o.to - o.from) / 24));
  let best = 0;
  let bestScore = Infinity;
  for (let i = 0; i < n; i++) {
    let hits = 0;
    let off = 0;
    let more = 0;
    for (let f = o.from; f < o.to; f += step) {
      const a = anchor(f, i);
      if (!a) continue;
      if (extra) more += extra(f, i);
      const [cx, cy] = a;
      const cam = cameraAt(p, f);
      const r = tokenRadiusPx(cam.w, p.width, p.height, p.orientation) + 6 * unit(p.width, p.height);
      if (cx - boxW / 2 < safe.x0 || cx + boxW / 2 > safe.x1 || cy - boxH / 2 < safe.y0 || cy + boxH / 2 > safe.y1) off++;
      for (const e of p.entities) {
        const pos = playerAt(p, e.id, f);
        if (!pos) continue;
        const [tx, ty] = worldToScreen(pos[0], pos[1], cam, p.width, p.height, p.orientation);
        const dx = Math.max(Math.abs(tx - cx) - boxW / 2, 0);
        const dy = Math.max(Math.abs(ty - cy) - boxH / 2, 0);
        if (dx * dx + dy * dy < r * r) hits++;
      }
      if (!hud.has(f)) hud.set(f, hudRects(p, f));
      for (const h of hud.get(f)!) {
        if (cx + boxW / 2 > h.x0 && cx - boxW / 2 < h.x1 && cy + boxH / 2 > h.y0 && cy - boxH / 2 < h.y1) hits++;
      }
    }
    const score = hits * 1000 + off * 300 + more + pref(i);
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  }
  return best;
}

// ---- area labels (zone / polygon) -----------------------------------------------------------------------------
// The anchor is a (u, v) position inside the bounding box of the part of the polygon that is on screen (clipped to
// the safe area shrunk by half the label box), so the label stays on the visible part of the zone while the camera
// moves, and its box always fits inside the safe area.

const GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
export const AREA_CANDIDATES: UV[] = GRID.flatMap((v) => GRID.map((u) => [u, v] as UV));

/** Visible (clipped) screen polygon of an area overlay at `frame`, or null when too little of it is on screen. */
export function visibleArea(o: Overlay, p: RenderProps, frame: number, boxW: number, boxH: number): P2[] | null {
  const cam = cameraAt(p, frame);
  const poly = (overlayPoints(o, frame) as P2[]).map(([x, y]) => worldToScreen(x, y, cam, p.width, p.height, p.orientation));
  if (poly.length < 3) return null;
  const safe = safeArea(p.width, p.height);
  const x0 = safe.x0 + boxW / 2;
  const x1 = safe.x1 - boxW / 2;
  const y0 = safe.y0 + boxH / 2;
  const y1 = safe.y1 - boxH / 2;
  if (x1 <= x0 || y1 <= y0) return null;
  const clip = clipPolygonToRect(poly, x0, y0, x1, y1);
  return clip.length >= 3 ? clip : null;
}

/** Screen anchor (label box centre) for bbox-relative slot `uv` at `frame`. */
export function areaAnchor(o: Overlay, p: RenderProps, frame: number, uv: UV, boxW: number, boxH: number): P2 | null {
  const vis = visibleArea(o, p, frame, boxW, boxH);
  if (!vis) return null;
  const [x0, y0, x1, y1] = bbox(vis);
  return [x0 + (x1 - x0) * uv[0], y0 + (y1 - y0) * uv[1]];
}

export function chooseAreaLabelUV(o: Overlay, p: RenderProps, boxW: number, boxH: number): UV {
  const i = chooseSlot(
    p,
    o,
    AREA_CANDIDATES.length,
    (f, k) => areaAnchor(o, p, f, AREA_CANDIDATES[k]!, boxW, boxH),
    boxW,
    boxH,
    (k) => Math.hypot(AREA_CANDIDATES[k]![0] - 0.5, AREA_CANDIDATES[k]![1] - 0.5),
    (f, k) => {
      // prefer anchors that sit inside the visible zone (not just inside its bounding box)
      const vis = visibleArea(o, p, f, boxW, boxH);
      const a = areaAnchor(o, p, f, AREA_CANDIDATES[k]!, boxW, boxH);
      return vis && a && !inside(vis, a[0], a[1]) ? 60 : 0;
    },
  );
  return AREA_CANDIDATES[i]!;
}

// ---- path labels (run_arrow / pass_line / line): slots along the path, either side ------------------------------

/** (fraction along the path, side) — side +1 = the normal pointing screen-up (or left), -1 = the other side. */
export const PATH_SLOTS: [number, 1 | -1][] = [
  [0.5, 1], [0.5, -1], [0.35, 1], [0.65, 1], [0.35, -1], [0.65, -1], [0.2, 1], [0.8, 1], [0.2, -1], [0.8, -1],
];

/** Screen path of a path overlay at `frame` (curved paths use the same spline as the renderer). */
export function screenPath(o: Overlay, p: RenderProps, frame: number, curved: boolean): P2[] {
  const cam = cameraAt(p, frame);
  const pts = (overlayPoints(o, frame) as P2[]).map(([x, y]) => worldToScreen(x, y, cam, p.width, p.height, p.orientation));
  return curved && pts.length >= 3 ? catmullRom(pts, 3) : pts;
}

/** Centre of a path label box for slot (t, side), `off` px from the path. */
export function pathSlotPoint(path: P2[], t: number, side: 1 | -1, off: number): P2 | null {
  if (path.length < 2) return null;
  const { p, angle } = pointAt(path, polyLength(path) * t);
  let nx = -Math.sin(angle);
  let ny = Math.cos(angle);
  if (ny > 0 || (ny === 0 && nx > 0)) {
    nx = -nx;
    ny = -ny;
  }
  return [p[0] + nx * off * side, p[1] + ny * off * side];
}

/** Label offset from a path: enough for the box to clear the stroke whatever the path direction. */
export function pathLabelOffset(boxW: number, boxH: number, angle: number, u: number): number {
  // half-extent of the box along the path normal + a 14 px (1080p) gap
  return Math.abs(Math.sin(angle)) * (boxW / 2) + Math.abs(Math.cos(angle)) * (boxH / 2) + 14 * u;
}

export function choosePathSlot(o: Overlay, p: RenderProps, curved: boolean, boxW: number, boxH: number): number {
  const u = unit(p.width, p.height);
  return chooseSlot(
    p,
    o,
    PATH_SLOTS.length,
    (f, k) => {
      const path = screenPath(o, p, f, curved);
      if (path.length < 2) return null;
      const [t, side] = PATH_SLOTS[k]!;
      const ang = pointAt(path, polyLength(path) * t).angle;
      return pathSlotPoint(path, t, side, pathLabelOffset(boxW, boxH, ang, u));
    },
    boxW,
    boxH,
    (k) => k * 0.01,
  );
}
