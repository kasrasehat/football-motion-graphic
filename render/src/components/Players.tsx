import React from "react";
import type { RenderProps, TeamTheme } from "../generated/render_props";
import { TITLE_STACK } from "../fonts";
import { rgba } from "../lib/colors";
import { placePlayerLabels, screenTokens } from "../lib/playerLabels";
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
      {screenTokens(props, frame).map(({ e, x, y }) => (
        <PlayerToken key={e.id} x={x} y={y} r={pj.tokenR} team={props.theme.teams[e.team]} number={e.number} u={pj.u} shadowId={shadowId} />
      ))}
    </svg>
  );
};

/**
 * Optional entity labels (e.g. player names) as small dark pills, placed by lib/playerLabels.ts. Drawn above all
 * overlays so rings, arrows and spotlights never cut through the text.
 */
export const PlayerLabels: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const pj = useProjector();
  const items = placePlayerLabels(props, frame);
  if (items.length === 0) return null;
  return (
    <svg width={pj.width} height={pj.height} style={{ position: "absolute", left: 0, top: 0 }}>
      {items.map((l) => {
        const w = l.x1 - l.x0;
        const h = l.y1 - l.y0;
        const accent = props.theme.teams[l.team].fill;
        return (
          <g key={l.id}>
            {l.leader ? (
              <>
                <line x1={l.leader[0][0]} y1={l.leader[0][1]} x2={l.leader[1][0]} y2={l.leader[1][1]} stroke="#000" strokeOpacity={0.4} strokeWidth={4 * pj.u} strokeLinecap="round" />
                <line x1={l.leader[0][0]} y1={l.leader[0][1]} x2={l.leader[1][0]} y2={l.leader[1][1]} stroke={accent} strokeWidth={2 * pj.u} strokeLinecap="round" />
              </>
            ) : null}
            <rect x={l.x0} y={l.y0} width={w} height={h} rx={4 * pj.u} fill={rgba(props.theme.panel, 0.86)} />
            <rect x={l.x0} y={l.y0 + h - 3 * pj.u} width={w} height={3 * pj.u} rx={1.5 * pj.u} fill={accent} />
            <text
              x={l.x0 + w / 2}
              y={l.y0 + h / 2 + l.fontSize * 0.34}
              textAnchor="middle"
              fontFamily={TITLE_STACK}
              fontWeight={600}
              fontSize={l.fontSize}
              letterSpacing="0.04em"
              fill={props.theme.ink}
            >
              {l.text}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
