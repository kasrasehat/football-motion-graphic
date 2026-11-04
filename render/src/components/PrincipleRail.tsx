import React from "react";
import type { RenderProps } from "../generated/render_props";
import { TITLE_STACK } from "../fonts";
import { rgba } from "../lib/colors";
import { unit } from "../lib/layout";
import { RAIL_BALL_GAP, RAIL_BALL_LH, RAIL_BALL_LS, RAIL_NAME_LH, RAIL_NAME_LS, RAIL_TITLE_LH, RAIL_TITLE_LS, railMetrics } from "../lib/rail";
import { TeamLockup } from "./graphics/common";

type Side = "H" | "A";

/** A player in the panel, drawn like their token on the pitch: team fill, team ring, shirt number. */
const NumberChip: React.FC<{ props: RenderProps; team: Side; number: number; size: number }> = ({ props, team, number, size }) => {
  const t = props.theme.teams[team];
  const digits = String(number);
  return (
    <div
      style={{
        width: size,
        height: size,
        flex: "none",
        boxSizing: "border-box",
        borderRadius: "50%",
        background: t.fill,
        border: `${Math.max(1, size * 0.07)}px solid ${t.ring}`,
        color: t.text,
        fontFamily: TITLE_STACK,
        fontWeight: 800,
        fontSize: size * (digits.length > 1 ? 0.5 : 0.58),
        lineHeight: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {digits}
    </div>
  );
};

/**
 * Key panel of the tactic still: the whole title, the team colours, who has the ball, then every principle with its
 * whole name and the players it involves. It sits beside the pitch (the camera leaves `rect` free), so no text about
 * the tactic can land on a player.
 */
export const PrincipleRailPanel: React.FC<{ props: RenderProps }> = ({ props }) => {
  const rail = props.principleRail;
  if (!rail) return null;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const m = railMetrics(rail, width, height);
  const [x0, y0, x1, y1] = rail.rect;
  return (
    <div
      style={{
        position: "absolute",
        left: x0,
        top: y0,
        width: x1 - x0,
        height: y1 - y0,
        boxSizing: "border-box",
        padding: m.pad,
        background: rgba(theme.panel, 0.96),
        borderRadius: 8 * u,
        borderTop: `${5 * u}px solid ${theme.accent}`,
        boxShadow: `0 ${6 * u}px ${22 * u}px rgba(0,0,0,0.4)`,
        overflow: "hidden",
        color: theme.ink,
        fontFamily: TITLE_STACK,
      }}
    >
      <div style={{ fontWeight: 800, fontSize: m.titleSize, lineHeight: RAIL_TITLE_LH, letterSpacing: `${RAIL_TITLE_LS}em`, textTransform: "uppercase", overflowWrap: "anywhere" }}>{rail.title}</div>
      <div
        style={{
          display: "flex",
          flexDirection: m.columns === 1 ? "column" : "row",
          alignItems: m.columns === 1 ? "flex-start" : "center",
          columnGap: m.colGap,
          rowGap: m.rowGap * 0.7,
          marginTop: m.rowGap * 0.7,
          marginBottom: m.rowGap * 0.7,
        }}
      >
        <TeamLockup theme={theme} u={u} fs={m.lockupSize} />
        <div style={{ display: "flex", alignItems: "center", gap: m.chipGap * RAIL_BALL_GAP, minWidth: 0 }}>
          <div style={{ width: m.ballSize, height: m.ballSize, flex: "none", borderRadius: "50%", background: "#f4f6f8", border: `${Math.max(1, 1.5 * u)}px solid #1a1f24`, boxSizing: "border-box" }} />
          <NumberChip props={props} team={rail.ball.team} number={rail.ball.number} size={m.chip} />
          {rail.ball.name ? <div style={{ fontWeight: 600, fontSize: m.lockupSize, lineHeight: RAIL_BALL_LH, letterSpacing: `${RAIL_BALL_LS}em`, textTransform: "uppercase", minWidth: 0, overflowWrap: "anywhere" }}>{rail.ball.name}</div> : null}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${m.columns}, ${m.columnWidth}px)`, columnGap: m.colGap, rowGap: m.rowGap }}>
        {rail.principles.map((pr) => (
          <div key={pr.id}>
            <div style={{ display: "flex", fontSize: m.nameSize, lineHeight: RAIL_NAME_LH, letterSpacing: `${RAIL_NAME_LS}em` }}>
              <div style={{ width: m.idWidth, flex: "none", fontWeight: 800, color: theme.accent }}>{pr.id}</div>
              <div style={{ fontWeight: 600, minWidth: 0, overflowWrap: "anywhere" }}>{pr.name}</div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: m.chipGap, marginTop: m.nameGap }}>
              {pr.players.map((pl) => (
                <NumberChip key={`${pl.team}${pl.number}`} props={props} team={pl.team} number={pl.number} size={m.chip} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
