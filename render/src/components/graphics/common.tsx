// Shared building blocks for the full-screen data graphics: lenient data access, the panel shell (backdrop, accent
// strip, kicker, title, team lock-up), fitted single-line text, team swatches and the mirrored comparison row.
import React from "react";
import type { Graphic, RenderProps, Theme } from "../../generated/render_props";
import { BODY_STACK, TITLE_STACK } from "../../fonts";
import { clamp01, easeOutCubic } from "../../lib/anim";
import { mix, rgba } from "../../lib/colors";
import { barFractions, formatValue, SHELL_1080, type ShellLayout } from "../../lib/graphics";
import { estimateTextWidth, fitFontSize } from "../../lib/layout";
import { CardBackdrop, cardEnvelope } from "../Cards";

export interface GraphicProps {
  g: Graphic;
  props: RenderProps;
  frame: number;
}

/** First string value among `keys` in graphic data (lenient about the data contract). */
export function pickString(data: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = data[k];
    if (typeof v === "string" && v.trim() !== "") return v;
  }
  return "";
}

export function pickStrings(data: Record<string, unknown>, keys: string[]): string[] {
  for (const k of keys) {
    const v = data[k];
    if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string" && x.trim() !== "");
  }
  return [];
}

export function asRecord(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

export function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

export function str(v: unknown): string {
  if (typeof v === "string") return v.trim();
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return "";
}

export type Side = "H" | "A";

/** Neutral colour for "no team" / draw marks. */
export function neutral(theme: Theme): string {
  return mix(theme.ink, theme.panel, 0.5);
}

export const abs = (x: number, y: number, w?: number, h?: number): React.CSSProperties => ({
  position: "absolute",
  left: x,
  top: y,
  ...(w === undefined ? {} : { width: w }),
  ...(h === undefined ? {} : { height: h }),
});

export interface TxtProps {
  text: string;
  /** box width (fixed); with `inline` it is the max width instead */
  w: number;
  size: number;
  /** smallest size the fit may shrink to before the ellipsis takes over (default 72% of size) */
  min?: number;
  family?: "title" | "body";
  weight?: 500 | 600 | 700 | 800;
  color: string;
  align?: "left" | "center" | "right";
  ls?: number;
  upper?: boolean;
  lh?: number;
  inline?: boolean;
  style?: React.CSSProperties;
}

/** One line of text, shrunk to fit `w` (down to `min`), then cut with an ellipsis by CSS. Never overflows. */
export const Txt: React.FC<TxtProps> = ({ text, w, size, min, family = "title", weight, color, align = "left", ls = 0, upper = false, lh = 1.2, inline = false, style }) => {
  const shown = upper ? text.toUpperCase() : text;
  const box = Math.max(1, w);
  const fs = Math.max(Math.min(size, min ?? size * 0.72), fitFontSize([shown], size, box, family, ls));
  return (
    <div
      style={{
        ...(inline ? { maxWidth: box, display: "inline-block" } : { width: box }),
        fontFamily: family === "title" ? TITLE_STACK : BODY_STACK,
        fontWeight: weight ?? (family === "title" ? 800 : 500),
        fontSize: fs,
        lineHeight: lh,
        letterSpacing: ls ? `${ls}em` : undefined,
        color,
        textAlign: align,
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        ...style,
      }}
    >
      {shown}
    </div>
  );
};

/** Multi-line paragraph clamped to `lines` with an ellipsis. */
export const Para: React.FC<{ text: string; w: number; size: number; color: string; lines?: number; align?: "left" | "center"; style?: React.CSSProperties }> = ({
  text,
  w,
  size,
  color,
  lines = 2,
  align = "left",
  style,
}) => (
  <div
    style={{
      width: w,
      fontFamily: BODY_STACK,
      fontWeight: 500,
      fontSize: size,
      lineHeight: 1.3,
      color,
      textAlign: align,
      display: "-webkit-box",
      WebkitLineClamp: lines,
      WebkitBoxOrient: "vertical",
      overflow: "hidden",
      ...style,
    }}
  >
    {text}
  </div>
);

/** Estimated number of lines (1..max) a paragraph needs at `size` in `w`. */
export function paraLines(text: string, w: number, size: number, max = 2): number {
  if (!text) return 0;
  return Math.max(1, Math.min(max, Math.ceil(estimateTextWidth(text, size, "body") / Math.max(1, w))));
}

/** Team colour block: fill with an inner ring in the team's ring colour. */
export const Swatch: React.FC<{ theme: Theme; side: Side | null; w: number; h: number; u: number; style?: React.CSSProperties }> = ({ theme, side, w, h, u, style }) => {
  const fill = side ? theme.teams[side].fill : neutral(theme);
  const ring = side ? theme.teams[side].ring : theme.ink;
  return (
    <div
      style={{
        width: w,
        height: h,
        flex: "none",
        background: fill,
        borderRadius: Math.min(w, h) * 0.3,
        boxShadow: `inset 0 0 0 ${Math.max(1, 2 * u)}px ${rgba(ring, 0.55)}`,
        ...style,
      }}
    />
  );
};

/** "▮ RMA  v  ARS ▮" chip for the panel header. */
export const TeamLockup: React.FC<{ theme: Theme; u: number; fs: number }> = ({ theme, u, fs }) => {
  const chip = (side: Side) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10 * u, flexDirection: side === "H" ? "row" : "row-reverse" }}>
      <Swatch theme={theme} side={side} w={12 * u} h={fs * 1.05} u={u} />
      <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: fs, lineHeight: 1.1, letterSpacing: "0.06em", color: theme.ink, whiteSpace: "nowrap" }}>
        {theme.teams[side].short.toUpperCase().slice(0, 4)}
      </div>
    </div>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 * u }}>
      {chip("H")}
      <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: fs * 0.8, color: rgba(theme.ink, 0.5) }}>v</div>
      {chip("A")}
    </div>
  );
};

/** Estimated width of TeamLockup. */
export function lockupWidth(theme: Theme, u: number, fs: number): number {
  const t = (s: string) => estimateTextWidth(s.toUpperCase().slice(0, 4), fs, "title", 0.06);
  return 2 * (12 * u + 10 * u) + t(theme.teams.H.short) + t(theme.teams.A.short) + 2 * 14 * u + fs * 0.5;
}

export interface ShellProps {
  gp: GraphicProps;
  L: ShellLayout;
  kicker: string;
  title: string;
  lockup?: boolean;
  children?: React.ReactNode;
}

/** Backdrop + centred panel with accent strip, kicker and title; children are laid out inside the body box. */
export const Shell: React.FC<ShellProps> = ({ gp, L, kicker, title, lockup = true, children }) => {
  const { g, props, frame } = gp;
  const env = cardEnvelope(g.from, g.to, frame, 8, 8);
  if (env <= 0) return null;
  const { width, height, theme } = props;
  const { u, panel } = L;
  const S = SHELL_1080;
  const pw = panel.x1 - panel.x0;
  const ph = panel.y1 - panel.y0;
  const innerW = pw - 2 * L.padX;
  const lockFs = 28 * u;
  const lockW = lockup ? lockupWidth(theme, u, lockFs) + 24 * u : 0;
  const lift = (1 - easeOutCubic((frame - g.from + 1) / 12)) * 28 * u;
  const rule = clamp01(easeOutCubic((frame - g.from - 2) / 14));
  const kickerY = S.padTop * u;
  const titleY = kickerY + S.kicker * 1.25 * u;
  return (
    <div style={{ position: "absolute", inset: 0, opacity: env }}>
      <CardBackdrop theme={theme} width={width} height={height} />
      <div
        style={{
          ...abs(panel.x0, panel.y0, pw, ph),
          transform: `translateY(${lift}px)`,
          background: `linear-gradient(180deg, ${rgba(mix(theme.panel, theme.ink, 0.05), 0.96)} 0%, ${rgba(theme.panel, 0.95)} 100%)`,
          borderRadius: 12 * u,
          boxShadow: `0 ${14 * u}px ${44 * u}px rgba(0,0,0,0.5)`,
          overflow: "hidden",
        }}
      >
        <div style={{ ...abs(0, 0, pw * rule, S.accent * u), background: theme.accent }} />
        {kicker ? (
          <Txt
            text={kicker}
            w={innerW - lockW}
            size={S.kicker * u}
            family="title"
            weight={600}
            ls={0.22}
            upper
            color={theme.accent}
            lh={1.25}
            style={abs(L.padX, kickerY)}
          />
        ) : null}
        <Txt text={title} w={innerW - lockW} size={S.title * u} min={S.title * u * 0.6} family="title" weight={800} ls={0.02} upper color={theme.ink} lh={1.05} style={abs(L.padX, titleY)} />
        {lockup ? (
          <div style={{ ...abs(pw - L.padX - lockW + 24 * u, titleY + (S.title * 1.05 * u - lockFs * 1.1) / 2) }}>
            <TeamLockup theme={theme} u={u} fs={lockFs} />
          </div>
        ) : null}
        <div style={{ ...abs(L.padX, L.headerH - S.ruleGap * u * 0.5, innerW, Math.max(1, 1.5 * u)), background: rgba(theme.ink, 0.1) }} />
        <div style={abs(L.padX, L.headerH, L.bodyW, L.bodyH)}>{children}</div>
      </div>
    </div>
  );
};

/** Short "nothing to show" line centred in a box. */
export const EmptyNote: React.FC<{ text: string; w: number; h: number; u: number; theme: Theme; x?: number; y?: number }> = ({ text, w, h, u, theme, x = 0, y = 0 }) => (
  <div style={{ ...abs(x, y, w, h), display: "flex", alignItems: "center", justifyContent: "center" }}>
    <Txt text={text} w={w} size={30 * u} family="body" weight={500} color={rgba(theme.ink, 0.6)} align="center" />
  </div>
);

export interface CompareRowProps {
  theme: Theme;
  u: number;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  home: unknown;
  away: unknown;
  unit?: unknown;
  /** reveal progress 0..1 (bars grow, text fades) */
  p: number;
  /** text scale (1 = 1080p sizes) */
  k?: number;
  valueW?: number;
}

/** Label over two bars growing out from the centre (home left, away right), values at the outer ends. */
export const CompareRow: React.FC<CompareRowProps> = ({ theme, u, x, y, w, h, label, home, away, unit: un, p, k = 1, valueW }) => {
  const labelFs = Math.max(18 * u, 26 * u * k);
  const valueFs = Math.max(28 * u, 50 * u * k);
  const barH = Math.max(10 * u, 20 * u * k);
  const vw = valueW ?? 160 * u;
  const gap = 18 * u;
  const regionX = vw + gap;
  const regionW = Math.max(0, w - 2 * regionX);
  const cx = regionX + regionW / 2;
  const centreGap = 8 * u;
  const half = Math.max(0, (regionW - centreGap) / 2);
  const block = labelFs * 1.2 + 8 * u * k + barH;
  const top = (h - block) / 2;
  const barY = top + labelFs * 1.2 + 8 * u * k;
  const [fh, fa] = barFractions(home, away);
  const grow = easeOutCubic(p);
  const fade = clamp01(p * 1.6);
  const hv = formatValue(home, un);
  const av = formatValue(away, un);
  const valueTop = barY + barH / 2 - valueFs * 0.55;
  const track = rgba(theme.ink, 0.07);
  return (
    <div style={{ ...abs(x, y, w, h), opacity: fade }}>
      <Txt text={label} w={regionW} size={labelFs} min={labelFs * 0.75} family="title" weight={600} ls={0.08} upper color={rgba(theme.ink, 0.78)} align="center" style={abs(regionX, top)} />
      <div style={{ ...abs(cx - centreGap / 2 - half, barY, half, barH), background: track, borderRadius: barH / 2 }} />
      <div style={{ ...abs(cx + centreGap / 2, barY, half, barH), background: track, borderRadius: barH / 2 }} />
      {fh !== null ? (
        <div
          style={{
            ...abs(cx - centreGap / 2 - half * fh * grow, barY, half * fh * grow, barH),
            background: theme.teams.H.fill,
            borderRadius: barH / 2,
          }}
        />
      ) : null}
      {fa !== null ? (
        <div style={{ ...abs(cx + centreGap / 2, barY, half * fa * grow, barH), background: theme.teams.A.fill, borderRadius: barH / 2 }} />
      ) : null}
      <Txt text={hv} w={vw} size={valueFs} min={valueFs * 0.6} family="title" weight={800} color={theme.ink} align="right" lh={1.1} style={abs(0, valueTop)} />
      <Txt text={av} w={vw} size={valueFs} min={valueFs * 0.6} family="title" weight={800} color={theme.ink} align="left" lh={1.1} style={abs(w - vw, valueTop)} />
    </div>
  );
};
