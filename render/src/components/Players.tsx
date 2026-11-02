import React from "react";
import type { RenderProps, TeamTheme } from "../generated/render_props";
import { TITLE_STACK } from "../fonts";
import { rgba } from "../lib/colors";
import { estimateTextWidth } from "../lib/layout";
import { playerAt } from "../lib/tracks";
import { useProjector } from "./CameraRig";

export interface PlayerTokenProps {
  x: number;
  y: number;
  r: number;
  team: TeamTheme;
  number: number;
  u: number;
  shadowId: string;
}

/** Filled disc (team fill) + ring (team ring) + shirt number (team text) with a soft drop shadow. */
export const PlayerToken: React.FC<PlayerTokenProps> = ({ x, y, r, team, number, u, shadowId }) => {
  const ringW = Math.max(1.5 * u, r * 0.13);
  const digits = String(number);
  const fs = r * (digits.length > 1 ? 0.98 : 1.12);
  return (
    <g>
      <circle cx={x + r * 0.08} cy={y + r * 0.16} r={r * 1.02} fill="#000000" opacity={0.42} filter={`url(#${shadowId})`} />
      <circle cx={x} cy={y} r={r} fill={team.fill} />
      <circle cx={x} cy={y} r={r - ringW / 2} fill="none" stroke={team.ring} strokeWidth={ringW} />
      <text
        x={x}
        y={y + fs * 0.35}
        textAnchor="middle"
        fontFamily={TITLE_STACK}
        fontWeight={800}
        fontSize={fs}
        fill={team.text}
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {digits}
      </text>
    </g>
  );
};

function visibleTokens(props: RenderProps, frame: number, pj: ReturnType<typeof useProjector>) {
  const r = pj.tokenR;
  const ordered = [...props.entities].sort((a, b) => (a.team === b.team ? 0 : a.team === "A" ? -1 : 1));
  const out: { e: RenderProps["entities"][number]; x: number; y: number }[] = [];
  for (const e of ordered) {
    const pos = playerAt(props, e.id, frame);
    if (!pos) continue;
    const [x, y] = pj.project(pos[0], pos[1]);
    if (x < -3 * r || y < -3 * r || x > pj.width + 3 * r || y > pj.height + 3 * r) continue;
    out.push({ e, x, y });
  }
  return out;
}

/** All 22 (or fewer) tokens at their per-frame track positions. Away drawn first so home sits on top. */
export const Players: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const pj = useProjector();
  const shadowId = `tok-shadow-${pj.width}x${pj.height}`;
  return (
    <svg width={pj.width} height={pj.height} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <filter id={shadowId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={Math.max(1, pj.tokenR * 0.14)} />
        </filter>
      </defs>
      {visibleTokens(props, frame, pj).map(({ e, x, y }) => (
        <PlayerToken key={e.id} x={x} y={y} r={pj.tokenR} team={props.theme.teams[e.team]} number={e.number} u={pj.u} shadowId={shadowId} />
      ))}
    </svg>
  );
};

/**
 * Optional entity labels (e.g. player names) as small dark pills just below each token. Drawn above all overlays so
 * rings, arrows and spotlights never cut through the text.
 */
export const PlayerLabels: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const pj = useProjector();
  const items = visibleTokens(props, frame, pj).filter(({ e }) => e.label);
  if (items.length === 0) return null;
  const r = pj.tokenR;
  const fs = Math.max(19 * pj.u, r * 0.6);
  const padX = 8 * pj.u;
  const h = fs * 1.15 + 6 * pj.u;
  return (
    <svg width={pj.width} height={pj.height} style={{ position: "absolute", left: 0, top: 0 }}>
      {items.map(({ e, x, y }) => {
        const text = e.label!.toUpperCase();
        const w = estimateTextWidth(text, fs, "title", 0.04) + 2 * padX;
        const top = y + r * 1.08;
        const accent = props.theme.teams[e.team].fill;
        return (
          <g key={e.id}>
            <rect x={x - w / 2} y={top} width={w} height={h} rx={4 * pj.u} fill={rgba(props.theme.panel, 0.86)} />
            <rect x={x - w / 2} y={top + h - 3 * pj.u} width={w} height={3 * pj.u} rx={1.5 * pj.u} fill={accent} />
            <text
              x={x}
              y={top + h / 2 + fs * 0.34}
              textAnchor="middle"
              fontFamily={TITLE_STACK}
              fontWeight={600}
              fontSize={fs}
              letterSpacing="0.04em"
              fill={props.theme.ink}
            >
              {text}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
