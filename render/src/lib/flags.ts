// Generated team flags and kit palettes: everything is derived from the team's kit colours in the theme (fill, ring,
// number colour). No images, no badges, nothing fetched. Pure functions, unit-tested in render/test/flags.test.ts.
import type { Theme } from "../generated/render_props";
import { contrastRatio, mix } from "./colors";
import { cardTeamFill, kitOutline } from "./graphics";

export type FlagSide = "H" | "A";

/** Width / height of a flag. */
export const FLAG_ASPECT = 1.5;
/** Contrast below which two kit colours are treated as "the same" on the flag. */
const DISTINCT = 1.45;

export interface FlagColors {
  /** main field: the shirt colour */
  field: string;
  /** hoist band: the trim (ring) colour, or the number colour, or a tint of the field when neither stands off it */
  band: string;
  /** thin pinstripe between band and field, or null when it would not add a third colour */
  stripe: string | null;
  /** outline that keeps the flag off a dark card (kitOutline: the trim, or a light edge for dark kits) */
  edge: string;
}

/** The colours of a team's flag, all from its kit. */
export function flagColors(theme: Theme, side: FlagSide): FlagColors {
  const t = theme.teams[side];
  const field = t.fill;
  let band: string;
  if (contrastRatio(t.ring, field) >= DISTINCT) band = t.ring;
  else if (contrastRatio(t.text, field) >= DISTINCT) band = t.text;
  else band = mix(field, contrastRatio("#ffffff", field) >= contrastRatio("#000000", field) ? "#ffffff" : "#000000", 0.45);
  const third = t.text;
  const stripe = contrastRatio(third, field) >= DISTINCT && contrastRatio(third, band) >= DISTINCT ? third : null;
  return { field, band, stripe, edge: kitOutline(theme, side) };
}

export interface FlagShape {
  /** whole outline (swallowtail pennant), SVG path */
  outline: string;
  /** hoist band polygon */
  band: string;
  /** pinstripe polygon */
  stripe: string;
  /** shading stops along x: [offset 0..1, signed shade -1..1] (negative = shadow, positive = highlight) */
  shade: [number, number][];
}

/** Share of the width taken by the hoist band, the pinstripe and the swallowtail notch. */
export const FLAG_BAND = 0.3;
export const FLAG_STRIPE = 0.055;
export const FLAG_NOTCH = 0.2;
const SEGMENTS = 24;

const f2 = (v: number) => (Math.round(v * 100) / 100).toString();

/**
 * Geometry of a swallowtail pennant `w` x `h` waving with `phase` (radians) and amplitude `amp` (share of h). Each
 * column is shifted vertically by the same wave, so bands stay straight relative to the cloth; the hoist is fixed.
 * Pure: same inputs, same strings.
 */
export function flagShape(w: number, h: number, phase = 0, amp = 0): FlagShape {
  const off = (x: number) => (amp === 0 ? 0 : amp * h * Math.sin((x / w) * Math.PI * 2.2 - phase) * Math.min(1, (x / w) * 1.6));
  const xs = (x0: number, x1: number) => Array.from({ length: SEGMENTS + 1 }, (_, i) => x0 + ((x1 - x0) * i) / SEGMENTS);
  const strip = (x0: number, x1: number) => {
    const top = xs(x0, x1).map((x) => `${f2(x)},${f2(off(x))}`);
    const bot = xs(x0, x1)
      .reverse()
      .map((x) => `${f2(x)},${f2(h + off(x))}`);
    return `M${top.join(" L")} L${bot.join(" L")} Z`;
  };
  const tip = w * (1 - FLAG_NOTCH);
  const top = xs(0, w).map((x) => `${f2(x)},${f2(off(x))}`);
  const bot = xs(0, w)
    .reverse()
    .map((x) => `${f2(x)},${f2(h + off(x))}`);
  const outline = `M${top.join(" L")} L${f2(tip)},${f2(h / 2 + off(tip))} L${bot.join(" L")} Z`;
  const bandW = w * FLAG_BAND;
  const shade: [number, number][] = [];
  for (let i = 0; i <= 10; i++) {
    const x = i / 10;
    // slope of the wave: cloth facing up catches the light, facing down falls into shadow
    const s = amp === 0 ? 0.35 - x * 0.7 : -Math.cos(x * Math.PI * 2.2 - phase) * Math.min(1, x * 1.6 + 0.25);
    shade.push([x, Math.max(-1, Math.min(1, s))]);
  }
  return { outline, band: strip(0, bandW), stripe: strip(bandW, bandW + w * FLAG_STRIPE), shade };
}

// ---------------------------------------------------------------------------------------------------------------
// Kit palettes for the card backdrops and rules
// ---------------------------------------------------------------------------------------------------------------

/** The colour a team tints a backdrop or a rule with: its card-safe fill (dark kits fall back to their trim). */
export function kitTint(theme: Theme, side: FlagSide): string {
  return cardTeamFill(theme, side);
}

/** The lightest colour of the card backdrop (centre of the radial gradient in `CardBackdrop`). */
export function backdropLift(theme: Theme): string {
  return mix(theme.panel, theme.pitch.grass, 0.28);
}

export const KIT_WASH_MAX = 0.2;
/** Contrast the theme ink keeps over the most tinted part of the backdrop (> 4.5 so 86% subtitles stay above 4.5). */
export const KIT_WASH_INK_CONTRAST = 7;

/**
 * Opacity of a team's kit wash on the card backdrop: up to `KIT_WASH_MAX`, lowered in steps until the ink still reads
 * at `KIT_WASH_INK_CONTRAST`:1 over the tinted backdrop at its lightest. Light kits (white, yellow) get a fainter wash.
 */
export function kitWashAlpha(theme: Theme, side: FlagSide): number {
  const tint = kitTint(theme, side);
  const lift = backdropLift(theme);
  for (let a = KIT_WASH_MAX; a > 0.0001; a -= 0.02) {
    if (contrastRatio(theme.ink, mix(lift, tint, a)) >= KIT_WASH_INK_CONTRAST) return Math.round(a * 1000) / 1000;
  }
  return 0;
}

/** Diagonal seam of the kit split backdrop: top and bottom x of the line between the home and away halves. */
export function kitSeam(width: number, height: number): { top: number; bottom: number } {
  const lean = Math.min(width, height) * 0.12;
  return { top: width / 2 + lean, bottom: width / 2 - lean };
}

/**
 * Segments of a kit rule as [colour, share of the width]: home and away halves, with a short accent between them only
 * when the accent stands apart from both kit colours (a gold accent next to a gold kit would just lengthen the kit).
 */
export function kitRule(theme: Theme): [string, number][] {
  const h = kitTint(theme, "H");
  const a = kitTint(theme, "A");
  const apart = (c: string) => contrastRatio(theme.accent, c) >= 1.5;
  if (apart(h) && apart(a)) return [[h, 0.44], [theme.accent, 0.12], [a, 0.44]];
  return [[h, 0.5], [a, 0.5]];
}

/** Opacity of the kit tint at the outer ends of a data card's header (it fades out toward the centre and the body). */
export const KIT_HEADER_WASH = 0.08;
