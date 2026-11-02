import React from "react";
import type { Theme } from "../generated/render_props";
import { mix, rgba } from "../lib/colors";
import { PITCH_LENGTH_M as L, PITCH_WIDTH_M as W } from "../lib/projection";
import { useProjector } from "./CameraRig";

// FIFA Laws of the Game, Law 1 (metres)
const CENTRE_R = 9.15;
const PA_DEPTH = 16.5;
const PA_WIDTH = 40.32;
const GA_DEPTH = 5.5;
const GA_WIDTH = 18.32;
const SPOT_DIST = 11;
const CORNER_R = 1;
const GOAL_WIDTH = 7.32;
const GOAL_DEPTH = 2.0;
const LINE_M = 0.12;
const RUNOFF = 6;
const STRIPES = 18; // 9 per half, so the halfway line sits on a stripe boundary

/** D arc: the part of the 9.15 m circle around the penalty spot that lies outside the penalty area. */
function dArc(side: "left" | "right"): string {
  const half = Math.sqrt(CENTRE_R * CENTRE_R - (PA_DEPTH - SPOT_DIST) ** 2);
  const x = side === "left" ? PA_DEPTH : L - PA_DEPTH;
  const sweep = side === "left" ? 1 : 0;
  return `M${x} ${W / 2 - half} A${CENTRE_R} ${CENTRE_R} 0 0 ${sweep} ${x} ${W / 2 + half}`;
}

function cornerArcs(): string {
  const r = CORNER_R;
  return [
    `M${r} 0 A${r} ${r} 0 0 1 0 ${r}`,
    `M${L - r} 0 A${r} ${r} 0 0 0 ${L} ${r}`,
    `M0 ${W - r} A${r} ${r} 0 0 1 ${r} ${W}`,
    `M${L} ${W - r} A${r} ${r} 0 0 0 ${L - r} ${W}`,
  ].join(" ");
}

function boxes(): string {
  const pa0 = (W - PA_WIDTH) / 2;
  const ga0 = (W - GA_WIDTH) / 2;
  return [
    `M0 ${pa0} H${PA_DEPTH} V${pa0 + PA_WIDTH} H0`,
    `M${L} ${pa0} H${L - PA_DEPTH} V${pa0 + PA_WIDTH} H${L}`,
    `M0 ${ga0} H${GA_DEPTH} V${ga0 + GA_WIDTH} H0`,
    `M${L} ${ga0} H${L - GA_DEPTH} V${ga0 + GA_WIDTH} H${L}`,
  ].join(" ");
}

function goals(): string {
  const g0 = (W - GOAL_WIDTH) / 2;
  return [
    `M0 ${g0} H${-GOAL_DEPTH} V${g0 + GOAL_WIDTH} H0`,
    `M${L} ${g0} H${L + GOAL_DEPTH} V${g0 + GOAL_WIDTH} H${L}`,
  ].join(" ");
}

function goalNets(): string {
  const g0 = (W - GOAL_WIDTH) / 2;
  const parts: string[] = [];
  for (const [xa, xb] of [
    [-GOAL_DEPTH, 0],
    [L, L + GOAL_DEPTH],
  ] as const) {
    for (let y = g0 + 0.61; y < g0 + GOAL_WIDTH; y += 0.61) parts.push(`M${xa} ${y.toFixed(3)} H${xb}`);
    for (let x = xa + 0.5; x < xb; x += 0.5) parts.push(`M${x} ${g0} V${g0 + GOAL_WIDTH}`);
  }
  return parts.join(" ");
}

/** Grass surround + striped run-off + FIFA markings, all in world metres under the camera matrix. */
export const Pitch: React.FC<{ theme: Theme; opacity?: number }> = ({ theme, opacity = 1 }) => {
  const pj = useProjector();
  const { grass, stripe, line } = theme.pitch;
  const surround = mix(grass, theme.panel, 0.62);
  // Line width: true 12 cm, but never thinner than 2 px at 1080p so it stays crisp when zoomed out.
  const lw = Math.max(LINE_M, (2.2 * pj.u) / pj.s);
  const band = L / STRIPES;
  const stripes: React.ReactNode[] = [];
  for (let i = -2; i < STRIPES + 2; i++) {
    if (i % 2 === 0) continue;
    stripes.push(<rect key={i} x={i * band} y={-RUNOFF} width={band} height={W + 2 * RUNOFF} fill={stripe} />);
  }
  const lineStyle = {
    fill: "none",
    stroke: line,
    strokeWidth: lw,
    strokeLinecap: "butt" as const,
    strokeLinejoin: "miter" as const,
  };
  const gid = `pitch-${pj.width}x${pj.height}`;
  return (
    <svg
      width={pj.width}
      height={pj.height}
      style={{ position: "absolute", left: 0, top: 0, opacity }}
      shapeRendering="geometricPrecision"
    >
      <defs>
        <clipPath id={`${gid}-runoff`}>
          <rect x={-RUNOFF} y={-RUNOFF} width={L + 2 * RUNOFF} height={W + 2 * RUNOFF} />
        </clipPath>
        <radialGradient id={`${gid}-light`} cx="50%" cy="45%" r="75%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity={0.06} />
          <stop offset="55%" stopColor="#000000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000000" stopOpacity={0.34} />
        </radialGradient>
      </defs>
      <rect x={0} y={0} width={pj.width} height={pj.height} fill={surround} />
      <g transform={pj.matrix}>
        <rect
          x={-RUNOFF - 0.6}
          y={-RUNOFF - 0.6}
          width={L + 2 * RUNOFF + 1.2}
          height={W + 2 * RUNOFF + 1.2}
          fill={rgba("#000000", 0.35)}
        />
        <g clipPath={`url(#${gid}-runoff)`}>
          <rect x={-RUNOFF} y={-RUNOFF} width={L + 2 * RUNOFF} height={W + 2 * RUNOFF} fill={grass} />
          {stripes}
        </g>
        <g opacity={0.92}>
          <path d={goalNets()} stroke={line} strokeWidth={lw * 0.35} opacity={0.35} fill="none" />
          <rect x={0} y={0} width={L} height={W} {...lineStyle} />
          <path d={`M${L / 2} 0 V${W}`} {...lineStyle} />
          <circle cx={L / 2} cy={W / 2} r={CENTRE_R} {...lineStyle} />
          <circle cx={L / 2} cy={W / 2} r={Math.max(0.25, lw * 1.6)} fill={line} />
          <path d={boxes()} {...lineStyle} />
          <circle cx={SPOT_DIST} cy={W / 2} r={Math.max(0.22, lw * 1.5)} fill={line} />
          <circle cx={L - SPOT_DIST} cy={W / 2} r={Math.max(0.22, lw * 1.5)} fill={line} />
          <path d={`${dArc("left")} ${dArc("right")}`} {...lineStyle} />
          <path d={cornerArcs()} {...lineStyle} />
          <path d={goals()} {...lineStyle} strokeWidth={lw * 1.25} strokeLinejoin="round" />
        </g>
      </g>
      <rect x={0} y={0} width={pj.width} height={pj.height} fill={`url(#${gid}-light)`} />
    </svg>
  );
};
