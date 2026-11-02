// Screen layout of the HUD (captions, scene lower-third, pause badge) as pure functions. The components use these for
// placement, and overlay label placement uses hudRects() to stay clear of them.
import type { Caption, RenderProps, Scene } from "../generated/render_props";
import { activeCaption, CAPTION_PAD_X_1080, captionFontSize } from "./captions";
import { estimateTextWidth, fitFontSize, safeArea, unit, type Rect } from "./layout";
import { spanAt } from "./tracks";

export const CAPTION_LINE_HEIGHT = 1.3;
export const CAPTION_PAD_Y_1080 = 16;
/** The lower-third shows for the first ~2 s (60 frames) of each scene, or the whole scene if shorter. */
export const SCENE_TITLE_FRAMES = 60;

/** Height in px of the caption box for `c`. */
export function captionBoxHeight(c: Caption, width: number, height: number): number {
  const fs = captionFontSize(c.lines, width, height);
  return Math.min(2, c.lines.length) * fs * CAPTION_LINE_HEIGHT + 2 * CAPTION_PAD_Y_1080 * unit(width, height);
}

/** Approximate caption box on screen (centred in the safe area, at its bottom or top edge). */
export function captionRect(c: Caption, width: number, height: number): Rect {
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const fs = captionFontSize(c.lines, width, height);
  const textW = Math.max(...c.lines.slice(0, 2).map((l) => estimateTextWidth(l, fs, "body")));
  const w = Math.min(safe.x1 - safe.x0, textW + 2 * CAPTION_PAD_X_1080 * u);
  const h = captionBoxHeight(c, width, height);
  const x0 = (width - w) / 2;
  return c.place === "top" ? { x0, y0: safe.y0, x1: x0 + w, y1: safe.y0 + h } : { x0, y0: safe.y1 - h, x1: x0 + w, y1: safe.y1 };
}

export function sceneTitleWindow(s: Scene): [number, number] {
  return [s.from, s.from + Math.min(SCENE_TITLE_FRAMES, Math.max(0, s.to - s.from))];
}

export interface SceneTitleLayout {
  index: number;
  scene: Scene;
  window: [number, number];
  /** distance from the bottom edge of the frame to the bottom of the lower-third (px) */
  bottom: number;
  fontSize: number;
  rect: Rect;
}

/** Lower-third at bottom-left of the safe area, lifted above any bottom caption overlapping its window. */
export function sceneTitleLayout(p: RenderProps, frame: number): SceneTitleLayout | null {
  const index = p.scenes.findIndex((s) => {
    const [a, b] = sceneTitleWindow(s);
    return s.title.trim() !== "" && frame >= a && frame < b;
  });
  if (index < 0) return null;
  const scene = p.scenes[index]!;
  const [a, b] = sceneTitleWindow(scene);
  const { width, height } = p;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  let bottom = height - safe.y1;
  for (const c of p.captions) {
    if (c.place === "bottom" && c.from < b && c.to > a) {
      bottom = Math.max(bottom, height - safe.y1 + captionBoxHeight(c, width, height) + 18 * u);
    }
  }
  const title = scene.title.toUpperCase();
  const maxW = (safe.x1 - safe.x0) * (width > height ? 0.55 : 0.92);
  const fontSize = fitFontSize([title], 54 * u, maxW - 60 * u, "title", 0.03);
  const w = 9 * u + 42 * u + fontSize * 0.62 * 1.2 + 16 * u + estimateTextWidth(title, fontSize, "title", 0.03);
  const h = fontSize * 1.05 + 24 * u;
  const rect = { x0: safe.x0, y0: height - bottom - h, x1: safe.x0 + w, y1: height - bottom };
  return { index, scene, window: [a, b], bottom, fontSize, rect };
}

export const PAUSE_BADGE_FONT_1080 = 26;

/** Pause badge (top-right of the safe area) shown inside freeze spans. */
export function pauseBadgeRect(width: number, height: number): Rect {
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const fs = PAUSE_BADGE_FONT_1080 * u;
  const w = 32 * u + 17 * u + 10 * u + estimateTextWidth("PAUSED", fs, "title", 0.16);
  const h = 16 * u + fs * 1.1;
  return { x0: safe.x1 - w, y0: safe.y0, x1: safe.x1, y1: safe.y0 + h };
}

/** Every HUD rectangle on screen at `frame`. */
export function hudRects(p: RenderProps, frame: number): Rect[] {
  const out: Rect[] = [];
  const c = activeCaption(p.captions, frame);
  if (c) out.push(captionRect(c, p.width, p.height));
  const t = sceneTitleLayout(p, frame);
  if (t) out.push(t.rect);
  if (spanAt(p.freeze, frame)) out.push(pauseBadgeRect(p.width, p.height));
  return out;
}
