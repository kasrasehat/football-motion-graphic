// Caption selection and active-word logic (pure).
import type { Caption, CaptionWord } from "../generated/render_props";
import { fitFontSize, safeArea, unit } from "./layout";

export type WordState = "past" | "active" | "future";

/** The caption visible at `frame` (half-open [from, to)); the earliest-starting one wins on overlap. */
export function activeCaption(captions: Caption[], frame: number): Caption | null {
  let best: Caption | null = null;
  for (const c of captions) {
    if (frame >= c.from && frame < c.to && (best === null || c.from < best.from)) best = c;
  }
  return best;
}

/** Index of the word being spoken at `frame` (from <= frame < to), or -1 between words. */
export function activeWordIndex(c: Caption, frame: number): number {
  for (let i = 0; i < c.words.length; i++) {
    const w = c.words[i]!;
    if (frame >= w.from && frame < w.to) return i;
  }
  return -1;
}

export function wordState(w: CaptionWord, frame: number): WordState {
  if (frame >= w.to) return "past";
  if (frame >= w.from) return "active";
  return "future";
}

export interface CaptionToken {
  text: string;
  /** index into caption.words, or -1 when the caption has no word timing */
  index: number;
  state: WordState;
}

/** Words grouped into (at most 2) display lines. Falls back to the plain `lines` when there is no word timing. */
export function captionLines(c: Caption, frame: number): CaptionToken[][] {
  const nLines = Math.min(2, c.lines.length);
  if (c.words.length === 0) {
    return c.lines.slice(0, 2).map((l) => l.split(/\s+/).filter(Boolean).map((t) => ({ text: t, index: -1, state: "past" as WordState })));
  }
  const out: CaptionToken[][] = Array.from({ length: nLines }, () => []);
  const active = activeWordIndex(c, frame);
  c.words.forEach((w, i) => {
    const line = Math.min(w.line, nLines - 1);
    const state: WordState = i === active ? "active" : wordState(w, frame) === "past" ? "past" : "future";
    out[line]!.push({ text: w.t, index: i, state });
  });
  return out.filter((l) => l.length > 0);
}

export const CAPTION_BASE_PX_1080 = 44;
export const CAPTION_PAD_X_1080 = 34;

/** Caption font size: 44 px at 1080p, reduced only if the longest line would not fit inside the 90% safe area. */
export function captionFontSize(lines: string[], width: number, height: number): number {
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const maxText = safe.x1 - safe.x0 - 2 * CAPTION_PAD_X_1080 * u;
  return fitFontSize(lines, CAPTION_BASE_PX_1080 * u, maxText, "body");
}
