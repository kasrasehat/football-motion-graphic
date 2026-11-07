import React from "react";
import { Img } from "remotion";
import type { RenderProps, Theme } from "../generated/render_props";
import { BODY_STACK, TITLE_STACK } from "../fonts";
import { clamp01, easeOutCubic } from "../lib/anim";
import { mix, rgba } from "../lib/colors";
import { backdropLift, kitRule, kitSeam, kitTint, kitWashAlpha, type FlagSide } from "../lib/flags";
import { teamCrest } from "../lib/graphics";
import { fitFontSize, safeArea, unit } from "../lib/layout";
import { flagWidth, TeamFlag } from "./TeamFlag";

/** Fade in/out envelope for a [from, to) card. */
export function cardEnvelope(from: number, to: number, frame: number, inFrames = 10, outFrames = 10): number {
  if (frame < from || frame >= to) return 0;
  return Math.min(easeOutCubic((frame - from + 1) / inFrames), easeOutCubic((to - frame) / outFrames));
}

/**
 * Panel backdrop with faint pitch markings, shared by full-screen cards. With `kits` (the default) it is split on a
 * slight diagonal: a wash of the home kit from the left edge and of the away kit from the right, each fading toward
 * the seam and kept faint enough (`kitWashAlpha`) that the theme ink still reads over it at 7:1.
 */
export const CardBackdrop: React.FC<{ theme: Theme; width: number; height: number; kits?: boolean }> = ({ theme, width, height, kits = true }) => {
  const u = unit(width, height);
  const deep = mix(theme.panel, "#000000", 0.35);
  const lift = backdropLift(theme);
  const r = Math.min(width, height) * 0.32;
  const seam = kitSeam(width, height);
  const mid = (seam.top + seam.bottom) / 2;
  const aH = kits ? kitWashAlpha(theme, "H") : 0;
  const aA = kits ? kitWashAlpha(theme, "A") : 0;
  const tH = kitTint(theme, "H");
  const tA = kitTint(theme, "A");
  return (
    <svg width={width} height={height} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <radialGradient id="card-bg" cx="50%" cy="42%" r="78%">
          <stop offset="0%" stopColor={lift} />
          <stop offset="100%" stopColor={deep} />
        </radialGradient>
        <linearGradient id="card-kit-h" x1={0} y1={0} x2={mid} y2={0} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={tH} stopOpacity={aH} />
          <stop offset="0.65" stopColor={tH} stopOpacity={aH * 0.45} />
          <stop offset="1" stopColor={tH} stopOpacity={aH * 0.2} />
        </linearGradient>
        <linearGradient id="card-kit-a" x1={width} y1={0} x2={mid} y2={0} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={tA} stopOpacity={aA} />
          <stop offset="0.65" stopColor={tA} stopOpacity={aA * 0.45} />
          <stop offset="1" stopColor={tA} stopOpacity={aA * 0.2} />
        </linearGradient>
      </defs>
      <rect x={0} y={0} width={width} height={height} fill="url(#card-bg)" />
      {aH > 0 ? <path d={`M0 0 H${seam.top} L${seam.bottom} ${height} H0 Z`} fill="url(#card-kit-h)" /> : null}
      {aA > 0 ? <path d={`M${seam.top} 0 H${width} V${height} H${seam.bottom} Z`} fill="url(#card-kit-a)" /> : null}
      {kits ? <path d={`M${seam.top} 0 L${seam.bottom} ${height}`} stroke={theme.ink} strokeOpacity={0.06} strokeWidth={2 * u} /> : null}
      <g stroke={theme.pitch.line} strokeOpacity={0.07} strokeWidth={3 * u} fill="none">
        <circle cx={width / 2} cy={height / 2} r={r} />
        {width >= height ? (
          <path d={`M${width / 2} 0 V${height}`} />
        ) : (
          <path d={`M0 ${height / 2} H${width}`} />
        )}
        <circle cx={width / 2} cy={height / 2} r={6 * u} fill={theme.pitch.line} fillOpacity={0.07} />
      </g>
    </svg>
  );
};

/** A rule in the kit colours (home, a short accent, away). `p` (0..1) draws it out from the centre. */
export const KitRule: React.FC<{ theme: Theme; w: number; h: number; p?: number; style?: React.CSSProperties }> = ({ theme, w, h, p = 1, style }) => {
  const shown = w * clamp01(p);
  return (
    <div style={{ width: w, height: h, display: "flex", justifyContent: "center", flex: "none", ...style }}>
      <div style={{ width: shown, height: h, display: "flex", gap: Math.max(1, h * 0.35), overflow: "hidden", borderRadius: h / 2 }}>
        {kitRule(theme).map(([c, share], i) => (
          <div key={i} style={{ flex: `${share} 1 0px`, minWidth: 0, height: h, background: c }} />
        ))}
      </div>
    </div>
  );
};

/** A crest in a square box, aspect kept. Remotion's Img holds the frame until the image is decoded. */
export const Crest: React.FC<{ src: string; size: number }> = ({ src, size }) => (
  <Img src={src} alt="" style={{ width: size, height: size, objectFit: "contain", flex: "none", display: "block" }} />
);

/** Frames the title-card flags take to fly in, and the delay of the away flag after the home flag. */
export const FLAG_IN_FRAMES = 16;
export const FLAG_AWAY_DELAY = 4;

/** Entry progress (0..1) of a side's flag on a card that starts at `from`. */
export function flagEntry(frame: number, from: number, side: FlagSide): number {
  return easeOutCubic((frame - from - 1 - (side === "A" ? FLAG_AWAY_DELAY : 0)) / FLAG_IN_FRAMES);
}

/** The two teams for the opening: crest (if supplied) or waving flag, short name under it, "v" between. */
export const TeamsHero: React.FC<{ theme: Theme; u: number; frame: number; from: number; flagH: number; uid: string }> = ({ theme, u, frame, from, flagH, uid }) => {
  const phase = (frame - from) * 0.17;
  const nameFs = flagH * 0.24;
  const one = (side: FlagSide) => {
    const p = flagEntry(frame, from, side);
    const crest = teamCrest(theme, side);
    const dx = (1 - p) * 140 * u * (side === "H" ? -1 : 1);
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 * u, opacity: clamp01(p * 1.3), transform: `translateX(${dx}px)` }}>
        {crest ? (
          <Crest src={crest} size={flagH * 1.15} />
        ) : (
          <TeamFlag theme={theme} side={side} h={flagH} uid={uid} phase={phase + (side === "A" ? 1.3 : 0)} amp={0.05} style={{ filter: `drop-shadow(0 ${8 * u}px ${14 * u}px rgba(0,0,0,0.45))` }} />
        )}
        <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: nameFs, lineHeight: 1, letterSpacing: "0.14em", color: theme.ink, whiteSpace: "nowrap" }}>
          {theme.teams[side].short.toUpperCase().slice(0, 4)}
        </div>
      </div>
    );
  };
  const vP = clamp01((frame - from - 6) / 10);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 46 * u }}>
      {one("H")}
      <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: flagH * 0.34, color: rgba(theme.ink, 0.55 * vP), marginBottom: nameFs + 12 * u }}>v</div>
      {one("A")}
    </div>
  );
};

export interface TitleBlockProps {
  props: RenderProps;
  frame: number;
  from: number;
  to: number;
  title: string;
  subtitle: string;
  kicker?: string;
}

/** Full-screen title: both teams' flags (or crests), big condensed headline, kit rule, subtitle. */
export const TitleBlock: React.FC<TitleBlockProps> = ({ props, frame, from, to, title, subtitle, kicker }) => {
  const env = cardEnvelope(from, to, frame);
  if (env <= 0) return null;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const maxW = (safe.x1 - safe.x0) * 0.92;
  const T = title.toUpperCase();
  const tfs = fitFontSize([T], (width > height ? 132 : 112) * u, maxW, "title", 0.01);
  const sfs = fitFontSize([subtitle], 40 * u, maxW, "body");
  const rise = (1 - easeOutCubic((frame - from + 1) / 14)) * 40 * u;
  const rule = easeOutCubic((frame - from - 3) / 14);
  const flagH = Math.min(width > height ? 150 * u : 170 * u, (maxW - 46 * u * 2 - 80 * u) / (2 * flagWidth(1)));
  return (
    <div style={{ position: "absolute", inset: 0, opacity: env }}>
      <CardBackdrop theme={theme} width={width} height={height} />
      <div
        style={{
          position: "absolute",
          left: safe.x0,
          width: safe.x1 - safe.x0,
          top: 0,
          bottom: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          transform: `translateY(${rise}px)`,
          textAlign: "center",
        }}
      >
        <div style={{ marginBottom: 34 * u }}>
          <TeamsHero theme={theme} u={u} frame={frame} from={from} flagH={flagH} uid={`title-${from}`} />
        </div>
        {kicker ? (
          <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 34 * u, letterSpacing: "0.22em", color: theme.accent, marginBottom: 10 * u }}>
            {kicker.toUpperCase()}
          </div>
        ) : null}
        <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: tfs, lineHeight: 0.98, letterSpacing: "0.01em", color: theme.ink, whiteSpace: "nowrap" }}>
          {T}
        </div>
        <KitRule theme={theme} w={300 * u} h={7 * u} p={rule} style={{ margin: `${22 * u}px 0` }} />
        {subtitle ? (
          <div style={{ fontFamily: BODY_STACK, fontWeight: 500, fontSize: sfs, color: rgba(theme.ink, 0.86), whiteSpace: "nowrap" }}>{subtitle}</div>
        ) : null}
      </div>
    </div>
  );
};

export const TitleCardView: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const tc = props.titleCard;
  if (!tc) return null;
  return <TitleBlock props={props} frame={frame} from={tc.from} to={tc.to} title={tc.title} subtitle={tc.subtitle} />;
};

export const EndCardView: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const ec = props.endCard;
  if (!ec) return null;
  const env = cardEnvelope(ec.from, ec.to, frame);
  if (env <= 0) return null;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const maxW = (safe.x1 - safe.x0) * 0.9;
  const fs = fitFontSize([ec.text.toUpperCase()], 84 * u, maxW, "title", 0.02);
  const flagH = 58 * u;
  const phase = (frame - ec.from) * 0.15;
  const rule = easeOutCubic((frame - ec.from - 2) / 14);
  const mark = (side: FlagSide) => {
    const crest = teamCrest(theme, side);
    return crest ? <Crest src={crest} size={flagH * 1.2} /> : <TeamFlag theme={theme} side={side} h={flagH} uid={`end-${ec.from}`} phase={phase + (side === "A" ? 1.3 : 0)} amp={0.04} />;
  };
  return (
    <div style={{ position: "absolute", inset: 0, opacity: env }}>
      <CardBackdrop theme={theme} width={width} height={height} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 26 * u,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 26 * u }}>
          {mark("H")}
          <KitRule theme={theme} w={170 * u} h={8 * u} p={rule} />
          {mark("A")}
        </div>
        <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: fs, color: theme.ink, letterSpacing: "0.02em", whiteSpace: "nowrap" }}>
          {ec.text.toUpperCase()}
        </div>
      </div>
    </div>
  );
};
