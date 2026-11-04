import type { OverlayStyle, Theme } from "../generated/render_props";

export type ColorKey = OverlayStyle["color"];

/** accent | warn | ink -> theme colour; H | A -> that team's fill. */
export function resolveColor(theme: Theme, key: ColorKey): string {
  if (key === "H" || key === "A") return theme.teams[key].fill;
  return theme[key];
}

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

export function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, alpha)).toFixed(3)})`;
}

/** Linear mix of two hex colours (t = 0 -> a, t = 1 -> b). */
export function mix(a: string, b: string, t: number): string {
  const A = hexToRgb(a);
  const B = hexToRgb(b);
  const c = A.map((v, i) => Math.round(v + ((B[i] ?? 0) - v) * t));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/** WCAG relative luminance. */
export function luminance(hex: string): number {
  const lin = (c: number) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio of two colours (1..21). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Pick whichever of `dark` / `light` contrasts better with `bg`. */
export function readableOn(bg: string, dark: string, light: string): string {
  return contrastRatio(bg, dark) >= contrastRatio(bg, light) ? dark : light;
}

/**
 * Casing for a team-coloured stroke on the pitch (`extra` = px at 1080p added to the stroke width): a colour that
 * stands off the grass gets a firm dark edge, one close to the grass in brightness a light halo so it still reads.
 */
export function pitchCasing(color: string, grass: string): { color: string; extra: number } {
  return contrastRatio(color, grass) < 3 ? { color: "rgba(255,255,255,0.85)", extra: 5 } : { color: "rgba(0,0,0,0.5)", extra: 4 };
}

/** Hex -> [hue 0..360, saturation 0..1, lightness 0..1]. */
export function hexToHsl(hex: string): [number, number, number] {
  const [r, g, b] = hexToRgb(hex).map((v) => v / 255) as [number, number, number];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return [h * 60, s, l];
}

export function hslToHex(h: number, s: number, l: number): string {
  const hue = (((h % 360) + 360) % 360) / 360;
  const S = Math.max(0, Math.min(1, s));
  const L = Math.max(0, Math.min(1, l));
  const f = (t0: number): number => {
    const q = L < 0.5 ? L * (1 + S) : L + S - L * S;
    const p = 2 * L - q;
    let t = t0;
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const c = [f(hue + 1 / 3), f(hue), f(hue - 1 / 3)].map((v) => Math.round(v * 255));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/** Same hue as `hex` with the given saturation and lightness (semantic colours derived from a theme colour). */
export function withHsl(hex: string, s: number, l: number): string {
  const [h] = hexToHsl(hex);
  return hslToHex(h, s, l);
}
