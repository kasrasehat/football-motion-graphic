// A team's generated flag: a swallowtail pennant in the kit colours (field = shirt, hoist band = trim, pinstripe =
// number colour), with a contrast-safe edge. It waves only when given a phase and an amplitude, both of which the
// caller derives from the frame number, so it stays a pure function of (frame, props).
import React from "react";
import type { Theme } from "../generated/render_props";
import { FLAG_ASPECT, flagColors, flagShape, type FlagSide } from "../lib/flags";

export interface TeamFlagProps {
  theme: Theme;
  side: FlagSide;
  /** flag height in px; the width is height x FLAG_ASPECT */
  h: number;
  /** unique within the frame (SVG gradient id) */
  uid: string;
  phase?: number;
  /** wave amplitude as a share of the height (0 = flat) */
  amp?: number;
  /** draw the hoist on the right (default: the away flag, so the two flags face each other) */
  mirror?: boolean;
  style?: React.CSSProperties;
}

export const TeamFlag: React.FC<TeamFlagProps> = ({ theme, side, h, uid, phase = 0, amp = 0, mirror = side === "A", style }) => {
  const w = h * FLAG_ASPECT;
  const c = flagColors(theme, side);
  const s = flagShape(w, h, phase, amp);
  const pad = Math.max(2, h * (amp + 0.06));
  const edgeW = Math.max(1, h * 0.045);
  const id = `flag-${uid}-${side}`;
  return (
    <svg
      width={w + 2 * pad}
      height={h + 2 * pad}
      viewBox={`${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`}
      style={{ display: "block", flex: "none", margin: -pad, overflow: "visible", ...style }}
      data-flag={side}
    >
      <defs>
        <linearGradient id={`${id}-shade`} x1="0" y1="0" x2={w} y2="0" gradientUnits="userSpaceOnUse">
          {s.shade.map(([o, v], i) => (
            <stop key={i} offset={o} stopColor={v >= 0 ? "#ffffff" : "#000000"} stopOpacity={Math.abs(v) * (v >= 0 ? 0.16 : 0.24)} />
          ))}
        </linearGradient>
        <clipPath id={`${id}-clip`}>
          <path d={s.outline} />
        </clipPath>
      </defs>
      <g transform={mirror ? `translate(${w} 0) scale(-1 1)` : undefined}>
      <path d={s.outline} fill={c.field} />
      <g clipPath={`url(#${id}-clip)`}>
        <path d={s.band} fill={c.band} />
        {c.stripe ? <path d={s.stripe} fill={c.stripe} /> : null}
        <path d={s.outline} fill={`url(#${id}-shade)`} />
      </g>
      <path d={s.outline} fill="none" stroke={c.edge} strokeOpacity={0.9} strokeWidth={edgeW} strokeLinejoin="round" />
      </g>
    </svg>
  );
};

/** Width of a TeamFlag of height `h`. */
export function flagWidth(h: number): number {
  return h * FLAG_ASPECT;
}
