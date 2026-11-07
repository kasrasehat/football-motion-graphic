import React from "react";
import { spring } from "remotion";
import type { Theme } from "../../generated/render_props";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { fitName, layoutMode, lineupRows, normLineup, revealFrame, revealProgress, shellLayout, type LineupPlayer, teamLabel } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asRecord, pickString, Shell, str, markWidth, TeamMark, Txt, type GraphicProps, type Side } from "./common";

const TOKEN_SPRING = { damping: 13, stiffness: 180, mass: 0.55 };

/** Stylised vertical pitch (own goal at the bottom), stretched to the box. */
const MiniPitch: React.FC<{ w: number; h: number; theme: Theme; u: number; id: string }> = ({ w, h, theme, u, id }) => {
  const sw = Math.max(1, 2.5 * u);
  const line = rgba(theme.pitch.line, 0.42);
  const bands = 10;
  const boxW = w * 0.56;
  const boxD = h * 0.15;
  const gaW = w * 0.26;
  const gaD = h * 0.055;
  const r = Math.min(w, h) * 0.13;
  return (
    <svg width={w} height={h} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <clipPath id={`lp-${id}`}>
          <rect x={0} y={0} width={w} height={h} rx={10 * u} />
        </clipPath>
        <linearGradient id={`lpshade-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#000000" stopOpacity={0.05} />
          <stop offset="100%" stopColor="#000000" stopOpacity={0.3} />
        </linearGradient>
      </defs>
      <g clipPath={`url(#lp-${id})`}>
        {Array.from({ length: bands }, (_, i) => (
          <rect key={i} x={0} y={(i * h) / bands} width={w} height={h / bands + 1} fill={i % 2 ? theme.pitch.stripe : theme.pitch.grass} />
        ))}
        <rect x={0} y={0} width={w} height={h} fill={`url(#lpshade-${id})`} />
        <g stroke={line} strokeWidth={sw} fill="none">
          <rect x={sw * 4} y={sw * 4} width={w - sw * 8} height={h - sw * 8} />
          <path d={`M${sw * 4} ${h / 2} H${w - sw * 4}`} />
          <circle cx={w / 2} cy={h / 2} r={r} />
          <rect x={(w - boxW) / 2} y={sw * 4} width={boxW} height={boxD} />
          <rect x={(w - boxW) / 2} y={h - sw * 4 - boxD} width={boxW} height={boxD} />
          <rect x={(w - gaW) / 2} y={sw * 4} width={gaW} height={gaD} />
          <rect x={(w - gaW) / 2} y={h - sw * 4 - gaD} width={gaW} height={gaD} />
        </g>
        <circle cx={w / 2} cy={h / 2} r={sw * 1.6} fill={line} />
      </g>
    </svg>
  );
};

interface Placed {
  p: LineupPlayer;
  x: number;
  y: number;
  slotW: number;
  order: number;
}

function place(rows: LineupPlayer[][], w: number, h: number, r: number, nameH: number, pad: number, u: number): Placed[] {
  const out: Placed[] = [];
  const nRows = rows.length;
  const yBottom = h - pad - nameH - r - 6 * u;
  const yTop = pad + r + 4 * u;
  let order = 0;
  rows.forEach((row, ri) => {
    const y = nRows <= 1 ? (yTop + yBottom) / 2 : yBottom - (ri * (yBottom - yTop)) / (nRows - 1);
    const k = row.length;
    const spacing = Math.min((w * 0.94) / Math.max(1, k), w * 0.3);
    row.forEach((p, j) => {
      out.push({ p, x: w / 2 + (j - (k - 1) / 2) * spacing, y, slotW: spacing, order: order++ });
    });
  });
  return out;
}

/** lineup_board: {home: [{name, number, position, line?, y?}], away: [...], home_formation?, away_formation?}. */
export const LineupBoard: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme, fps } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const L = shellLayout(width, height, { panelW: mode === "landscape" ? 1560 * u : undefined });
  const bw = L.bodyW;
  const bh = L.bodyH;
  const stacked = mode === "portrait";
  const gap = (stacked ? 28 : 36) * u;
  const blockW = stacked ? bw : (bw - gap) / 2;
  const blockH = stacked ? (bh - gap) / 2 : bh;
  const headH = 58 * u;
  const pitchW = blockW;
  const pitchH = blockH - headH - 10 * u;

  const team = (side: Side, idx: number) => {
    const players = normLineup(side === "H" ? d.home : d.away);
    const formation = str(side === "H" ? d.home_formation : d.away_formation);
    const rows = lineupRows(players, formation);
    const at = revealFrame(g, idx);
    const p = revealProgress(frame, at, 12);
    if (p <= 0) return null;
    const bx = stacked ? 0 : idx * (blockW + gap);
    const by = stacked ? idx * (blockH + gap) : 0;
    const maxRow = Math.max(1, ...rows.map((r) => r.length));
    const rowGap = (pitchH * 0.8) / Math.max(1, rows.length - 1);
    const spacing = Math.min((pitchW * 0.94) / maxRow, pitchW * 0.3);
    const r = Math.max(12 * u, Math.min(31 * u, rowGap * 0.27, spacing * 0.26));
    const nameFs = Math.max(15 * u, Math.min(23 * u, r * 0.78));
    const nameH = nameFs * 1.35;
    const placed = place(rows, pitchW, pitchH, r, nameH, 10 * u, u);
    const t = theme.teams[side];
    const formW = formation ? 140 * u : 0;
    return (
      <div key={side} style={{ ...abs(bx, by, blockW, blockH), opacity: clamp01(p * 1.4) }}>
        <div style={{ ...abs(0, 0, blockW - formW, headH), display: "flex", alignItems: "center", gap: 14 * u }}>
          <TeamMark theme={theme} side={side} h={34 * u} u={u} uid={g.id} />
          <Txt text={teamLabel(theme, side, blockW - formW - 26 * u - markWidth(34 * u), 40 * u, 0.03)} w={blockW - formW - 26 * u - markWidth(34 * u)} size={40 * u} upper ls={0.03} color={theme.ink} />
        </div>
        {formation ? (
          <Txt text={formation} w={formW} size={40 * u} color={theme.accent} align="right" ls={0.04} style={{ ...abs(blockW - formW, (headH - 48 * u) / 2) }} />
        ) : null}
        <div style={{ ...abs(0, headH + 10 * u, pitchW, pitchH), borderRadius: 10 * u, boxShadow: `0 ${6 * u}px ${18 * u}px rgba(0,0,0,0.35)` }}>
          <MiniPitch w={pitchW} h={pitchH} theme={theme} u={u} id={`${g.id}-${side}`} />
          {players.length === 0 ? (
            <div style={{ ...abs(0, 0, pitchW, pitchH), display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Txt text="Line-up not available" w={pitchW - 40 * u} size={30 * u} family="body" color={rgba(theme.ink, 0.8)} align="center" />
            </div>
          ) : null}
          {placed.map(({ p: pl, x, y, slotW, order }) => {
            const f = frame - at - 4 - order;
            if (f < 0) return null;
            const s = spring({ frame: f, fps, config: TOKEN_SPRING });
            const nameW = Math.max(20 * u, slotW - 4 * u);
            const shown = pl.name ? fitName(pl.name, nameW - 12 * u, nameFs, "title", 0.02, true) : "";
            return (
              <React.Fragment key={order}>
                <div
                  style={{
                    ...abs(x - r, y - r, 2 * r, 2 * r),
                    transform: `scale(${s})`,
                    borderRadius: "50%",
                    background: t.fill,
                    boxShadow: `inset 0 0 0 ${Math.max(1.5, r * 0.12)}px ${t.ring}, 0 ${3 * u}px ${8 * u}px rgba(0,0,0,0.45)`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: TITLE_STACK,
                    fontWeight: 800,
                    fontSize: r * 1.02,
                    lineHeight: 1,
                    color: t.text,
                  }}
                >
                  {pl.number === null ? "" : pl.number}
                </div>
                {shown ? (
                  <div style={{ ...abs(x - nameW / 2, y + r + 5 * u, nameW, nameH), display: "flex", justifyContent: "center", opacity: clamp01(s) }}>
                    <div
                      style={{
                        maxWidth: nameW,
                        boxSizing: "border-box",
                        padding: `0 ${6 * u}px`,
                        borderRadius: 4 * u,
                        background: "rgba(0,0,0,0.55)",
                        fontFamily: TITLE_STACK,
                        fontWeight: 600,
                        fontSize: nameFs,
                        lineHeight: 1.3,
                        letterSpacing: "0.02em",
                        color: theme.ink,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {shown.toUpperCase()}
                    </div>
                  </div>
                ) : null}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <Shell gp={gp} L={L} kicker="Line-ups" title={pickString(d, ["title", "headline"]) || "Expected line-ups"}>
      {team("H", 0)}
      {team("A", 1)}
    </Shell>
  );
};
