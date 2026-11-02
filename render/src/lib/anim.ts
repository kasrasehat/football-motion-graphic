// Overlay visibility and in/out animation state: a pure function of (overlay window, frame).
import type { Anim } from "../generated/render_props";

export const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);
export const easeOutCubic = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
export const easeInOutCubic = (t: number): number => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
/** Overshoots to ~1.1 then settles at 1 (used by "pop"). */
export const easeOutBack = (t: number): number => {
  const x = clamp01(t);
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
};

export interface Windowed {
  from: number;
  to: number;
  inAnim: Anim;
  outAnim: Anim;
}

export interface AnimState {
  /** from <= frame < to */
  visible: boolean;
  opacity: number;
  scale: number;
  /** Visible part of a path, as fractions of its length: [drawFrom, drawTo]. */
  drawFrom: number;
  drawTo: number;
  /** Frames since `from` (>= 0 while visible). */
  local: number;
}

const HIDDEN: AnimState = { visible: false, opacity: 0, scale: 0, drawFrom: 0, drawTo: 0, local: -1 };

/** Half-open visibility window [from, to). */
export function isVisible(w: { from: number; to: number }, frame: number): boolean {
  return frame >= w.from && frame < w.to;
}

/** In-progress fraction: reaches 1 on the last frame of the in-window; every frame of the window shows progress. */
export function inProgress(w: Windowed, frame: number): number {
  const n = w.inAnim.anim === "none" ? 0 : w.inAnim.frames;
  if (n <= 0) return 1;
  return clamp01((frame - w.from + 1) / n);
}

/** Out-remaining fraction: 1 until the out-window starts, then falls to 1/n on the last visible frame. */
export function outRemaining(w: Windowed, frame: number): number {
  const n = w.outAnim.anim === "none" ? 0 : w.outAnim.frames;
  if (n <= 0) return 1;
  return clamp01((w.to - frame) / n);
}

export function animState(w: Windowed, frame: number): AnimState {
  if (!isVisible(w, frame)) return HIDDEN;
  const p = inProgress(w, frame);
  const q = outRemaining(w, frame);
  let opacity = 1;
  let scale = 1;
  let drawFrom = 0;
  let drawTo = 1;
  switch (w.inAnim.anim) {
    case "draw":
      drawTo = easeInOutCubic(p);
      break;
    case "fade":
      opacity *= easeOutCubic(p);
      break;
    case "pop":
      scale *= easeOutBack(p);
      opacity *= clamp01(p * 2);
      break;
    case "none":
      break;
  }
  switch (w.outAnim.anim) {
    case "draw":
      // erase from the start so the tail chases the head
      drawFrom = 1 - easeInOutCubic(q);
      break;
    case "fade":
      opacity *= easeOutCubic(q);
      break;
    case "pop":
      scale *= easeOutCubic(q);
      opacity *= clamp01(q * 2);
      break;
    case "none":
      break;
  }
  return { visible: true, opacity, scale, drawFrom, drawTo, local: frame - w.from };
}

/** For overlays without a path (zone, ring, label, spotlight) a "draw" reveal is shown as a fade. */
export function nonPathOpacity(s: AnimState): number {
  return s.opacity * clamp01(s.drawTo - s.drawFrom);
}

/** Deterministic pulse in [0, 1) with the given period, derived only from the frame. */
export function pulsePhase(localFrame: number, period: number): number {
  const p = localFrame % period;
  return (p < 0 ? p + period : p) / period;
}
