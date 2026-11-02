// Pure overlay helpers: geometry at a frame, layer assignment, distance text.
import type { Overlay, Pt } from "../generated/render_props";

export type OverlayKind = Overlay["kind"];
export type Layer = "under" | "over";

/** World points (metres) of an overlay at `frame`. perFrame geometry is indexed by frame - from (clamped). */
export function overlayPoints(o: Overlay, frame: number): Pt[] {
  if ("static" in o.geom) return o.geom.static;
  const pf = o.geom.perFrame;
  if (pf.length === 0) return [];
  const i = Math.max(0, Math.min(pf.length - 1, Math.floor(frame - o.from)));
  return pf[i] ?? [];
}

/** Path-like overlays: drawn under the player tokens so tokens sit on top of arrows/lines. */
export const UNDER_KINDS: ReadonlySet<OverlayKind> = new Set(["zone", "polygon", "line", "pass_line", "run_arrow", "distance"]);
/** Focus overlays: drawn above tokens. */
export const OVER_KINDS: ReadonlySet<OverlayKind> = new Set(["spotlight", "ring", "label"]);
/** Kinds whose "draw" animation reveals a path progressively. */
export const PATH_KINDS: ReadonlySet<OverlayKind> = new Set(["run_arrow", "pass_line", "line", "polygon", "distance"]);

/** Euclidean distance (metres) between the first two points, formatted like "12.3 m". */
export function distanceText(points: Pt[], label: string | null): string {
  const a = points[0];
  const b = points[1];
  if (!a || !b) return label ?? "";
  const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const t = `${d.toFixed(1)} m`;
  return label ? `${label} · ${t}` : t;
}
