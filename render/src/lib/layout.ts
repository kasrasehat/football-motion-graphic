// Screen layout helpers: safe area, deterministic text-width estimates (no DOM measuring), box clamping.

export const FONT_TITLE = "Barlow Condensed";
export const FONT_BODY = "Inter";

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** 90% safe area (5% margin on every side). */
export function safeArea(width: number, height: number, fraction = 0.9): Rect {
  const mx = (width * (1 - fraction)) / 2;
  const my = (height * (1 - fraction)) / 2;
  return { x0: mx, y0: my, x1: width - mx, y1: height - my };
}

/** Size factor relative to 1080p: every px size in the components is authored at 1080p and multiplied by this. */
export function unit(width: number, height: number): number {
  return Math.min(width, height) / 1080;
}

type Family = "body" | "title";

// Approximate advance widths in em. Deliberately generous (estimates must over-, never under-shoot, so text that is
// fitted with them is never clipped).
const WIDTHS: Record<Family, { narrow: number; semi: number; lower: number; wide: number; upper: number; upperWide: number; digit: number; space: number; punct: number }> = {
  body: { narrow: 0.3, semi: 0.4, lower: 0.58, wide: 0.88, upper: 0.72, upperWide: 0.98, digit: 0.64, space: 0.29, punct: 0.36 },
  title: { narrow: 0.22, semi: 0.3, lower: 0.46, wide: 0.7, upper: 0.52, upperWide: 0.74, digit: 0.5, space: 0.22, punct: 0.28 },
};

function charWidth(ch: string, w: (typeof WIDTHS)["body"]): number {
  if (ch === " ") return w.space;
  if ("iljI|!.,:;'`".includes(ch)) return w.narrow;
  if ("ftrJ()[]-/\"".includes(ch)) return w.semi;
  if ("mw".includes(ch)) return w.wide;
  if ("MW".includes(ch)) return w.upperWide;
  if (ch >= "0" && ch <= "9") return w.digit;
  if (ch >= "A" && ch <= "Z") return w.upper;
  if (ch >= "a" && ch <= "z") return w.lower;
  if ("?&%@#+=*".includes(ch)) return w.upper;
  return w.punct + 0.25; // anything else (accents, symbols): assume wide-ish
}

/** Estimated rendered width in px of a single line of text. */
export function estimateTextWidth(
  text: string,
  fontSizePx: number,
  family: Family = "body",
  letterSpacingEm = 0,
  uppercase = false,
): number {
  const w = WIDTHS[family];
  const t = uppercase ? text.toUpperCase() : text;
  let em = 0;
  for (const ch of t) em += charWidth(ch, w) + letterSpacingEm;
  return em * fontSizePx;
}

/** Largest font size <= base so that every line fits in maxWidth. */
export function fitFontSize(
  lines: string[],
  base: number,
  maxWidth: number,
  family: Family = "body",
  letterSpacingEm = 0,
  uppercase = false,
): number {
  let size = base;
  for (const l of lines) {
    const w = estimateTextWidth(l, base, family, letterSpacingEm, uppercase);
    if (w > maxWidth) size = Math.min(size, (base * maxWidth) / w);
  }
  return size;
}

/** Clamp a box (top-left x,y; size w,h) into rect r. */
export function clampBox(x: number, y: number, w: number, h: number, r: Rect): [number, number] {
  const cx = Math.min(Math.max(x, r.x0), Math.max(r.x0, r.x1 - w));
  const cy = Math.min(Math.max(y, r.y0), Math.max(r.y0, r.y1 - h));
  return [cx, cy];
}
