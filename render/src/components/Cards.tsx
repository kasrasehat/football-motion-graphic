import React from "react";
import { Img } from "remotion";
import type { RenderProps, Theme } from "../generated/render_props";
import { BODY_STACK, TITLE_STACK } from "../fonts";
import { clamp01, easeOutCubic } from "../lib/anim";
import { mix, rgba } from "../lib/colors";
import { teamCrest } from "../lib/graphics";
import { fitFontSize, safeArea, unit } from "../lib/layout";

/** Fade in/out envelope for a [from, to) card. */
export function cardEnvelope(from: number, to: number, frame: number, inFrames = 10, outFrames = 10): number {
  if (frame < from || frame >= to) return 0;
  return Math.min(easeOutCubic((frame - from + 1) / inFrames), easeOutCubic((to - frame) / outFrames));
}

/** Panel backdrop with faint pitch markings, shared by full-screen cards. */
export const CardBackdrop: React.FC<{ theme: Theme; width: number; height: number }> = ({ theme, width, height }) => {
  const u = unit(width, height);
  const deep = mix(theme.panel, "#000000", 0.35);
  const lift = mix(theme.panel, theme.pitch.grass, 0.28);
  const r = Math.min(width, height) * 0.32;
  return (
    <svg width={width} height={height} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <radialGradient id="card-bg" cx="50%" cy="42%" r="78%">
          <stop offset="0%" stopColor={lift} />
          <stop offset="100%" stopColor={deep} />
        </radialGradient>
      </defs>
      <rect x={0} y={0} width={width} height={height} fill="url(#card-bg)" />
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

/** A crest in a square box, aspect kept. Remotion's Img holds the frame until the image is decoded. */
export const Crest: React.FC<{ src: string; size: number }> = ({ src, size }) => (
  <Img src={src} alt="" style={{ width: size, height: size, objectFit: "contain", flex: "none", display: "block" }} />
);

export interface TitleBlockProps {
  props: RenderProps;
  frame: number;
  from: number;
  to: number;
  title: string;
  subtitle: string;
  kicker?: string;
}

/** Full-screen title: big condensed headline, accent rule, subtitle. */
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
  const crests = [teamCrest(theme, "H"), teamCrest(theme, "A")].filter((c): c is string => c !== null);
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
        {crests.length > 0 ? (
          <div style={{ display: "flex", gap: 56 * u, marginBottom: 30 * u }}>
            {crests.map((c, i) => (
              <Crest key={i} src={c} size={170 * u} />
            ))}
          </div>
        ) : null}
        {kicker ? (
          <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 34 * u, letterSpacing: "0.22em", color: theme.accent, marginBottom: 10 * u }}>
            {kicker.toUpperCase()}
          </div>
        ) : null}
        <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: tfs, lineHeight: 0.98, letterSpacing: "0.01em", color: theme.ink, whiteSpace: "nowrap" }}>
          {T}
        </div>
        <div style={{ width: 220 * u * clamp01(rule), height: 7 * u, background: theme.accent, borderRadius: 4 * u, margin: `${22 * u}px 0` }} />
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
          gap: 22 * u,
        }}
      >
        <div style={{ display: "flex", gap: 14 * u }}>
          <div style={{ width: 46 * u, height: 8 * u, borderRadius: 4 * u, background: theme.teams.H.fill }} />
          <div style={{ width: 46 * u, height: 8 * u, borderRadius: 4 * u, background: theme.accent }} />
          <div style={{ width: 46 * u, height: 8 * u, borderRadius: 4 * u, background: theme.teams.A.fill }} />
        </div>
        <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: fs, color: theme.ink, letterSpacing: "0.02em", whiteSpace: "nowrap" }}>
          {ec.text.toUpperCase()}
        </div>
      </div>
    </div>
  );
};
