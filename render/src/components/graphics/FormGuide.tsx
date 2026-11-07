import React from "react";
import { spring } from "remotion";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { readableOn, rgba } from "../../lib/colors";
import { formPoints, layoutMode, normResults, resultColors, revealFrame, revealProgress, shellLayout, type FormResult, teamLabel } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asRecord, pickString, Shell, markWidth, TeamMark, Txt, type GraphicProps, type Side } from "./common";

const MAX_CHIPS = 10;
const CHIP_SPRING = { damping: 14, stiffness: 170, mass: 0.6 };

/** form_guide: {home: ["W"|"D"|"L"], away: [...]} (most recent last) - result chips + points, one reveal per team. */
export const FormGuide: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme, fps } = props;
  const d = asRecord(g.data);
  const teams: { side: Side; rs: FormResult[] }[] = [
    { side: "H", rs: normResults(d.home).slice(-MAX_CHIPS) },
    { side: "A", rs: normResults(d.away).slice(-MAX_CHIPS) },
  ];
  const N = Math.max(1, ...teams.map((t) => t.rs.length));
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const stacked = mode !== "landscape";
  const colors = resultColors(theme);
  const gap = 14 * u;
  const legendH = 40 * u;
  const rowGap = 22 * u;

  // landscape: [name | chips | points] per row; otherwise: [name ... points] over a full-width chip row
  const probe = shellLayout(width, height, { panelW: mode === "landscape" ? 1500 * u : undefined });
  const bw = probe.bodyW;
  const nameW = stacked ? bw - 260 * u : 400 * u;
  const ptsW = 210 * u;
  const chipsX = stacked ? 0 : nameW + 30 * u;
  const chipsW = stacked ? bw : bw - chipsX - ptsW - 30 * u;
  const chip = Math.min(stacked ? 128 * u : 108 * u, (chipsW - (N - 1) * gap) / N);
  const headH = stacked ? 96 * u : 0;
  const rowH = stacked ? headH + 16 * u + chip : Math.max(chip, 120 * u) + 24 * u;
  const L = shellLayout(width, height, { panelW: mode === "landscape" ? 1500 * u : undefined, bodyH: legendH + 2 * rowH + rowGap });
  const nChipsSpan = N * chip + (N - 1) * gap;
  const chipsRight = chipsX + (chipsW + nChipsSpan) / 2; // chip group centred; shorter rows stay right-aligned to it

  const legendStyle = { fontFamily: TITLE_STACK, fontWeight: 600 as const, fontSize: 20 * u, letterSpacing: "0.16em", color: rgba(theme.ink, 0.5), whiteSpace: "nowrap" as const };
  return (
    <Shell gp={gp} L={L} kicker="Form guide" title={pickString(d, ["title", "headline"]) || "Recent form"}>
      <div style={{ ...abs(chipsRight - nChipsSpan, 0, nChipsSpan, legendH), display: "flex", alignItems: "center", gap: 12 * u }}>
        <div style={legendStyle}>OLDER</div>
        <div style={{ flex: 1, height: Math.max(1, 2 * u), background: rgba(theme.ink, 0.18) }} />
        <div style={{ ...legendStyle, color: rgba(theme.ink, 0.75) }}>LATEST</div>
        <svg width={10 * u} height={14 * u} viewBox="0 0 10 14" style={{ flex: "none" }}>
          <path d="M0 0 L10 7 L0 14 Z" fill={rgba(theme.ink, 0.75)} />
        </svg>
      </div>
      {teams.map(({ side, rs }, ti) => {
        const at = revealFrame(g, ti);
        const p = revealProgress(frame, at, 12);
        if (p <= 0) return null;
        const y = legendH + ti * (rowH + rowGap);
        const pts = formPoints(rs);
        const chipY = stacked ? headH + 16 * u : (rowH - chip) / 2;
        const ptsBlock = (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", width: ptsW }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 * u }}>
              <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: (stacked ? 56 : 68) * u, lineHeight: 1, color: theme.ink }}>{rs.length ? pts : "–"}</div>
              <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: 26 * u, color: theme.accent, letterSpacing: "0.08em" }}>PTS</div>
            </div>
            <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 19 * u, letterSpacing: "0.14em", color: rgba(theme.ink, 0.55), marginTop: 4 * u, whiteSpace: "nowrap" }}>
              {`FROM LAST ${rs.length}`}
            </div>
          </div>
        );
        return (
          <div key={side} style={{ ...abs(0, y, bw, rowH), opacity: clamp01(p * 1.5) }}>
            <div style={{ ...abs(0, stacked ? (headH - 64 * u) / 2 : (rowH - 64 * u) / 2, nameW, 64 * u), display: "flex", alignItems: "center", gap: 16 * u }}>
              <TeamMark theme={theme} side={side} h={40 * u} u={u} uid={g.id} />
              <Txt text={teamLabel(theme, side, nameW - 16 * u - markWidth(40 * u), 48 * u, 0.02)} w={nameW - 16 * u - markWidth(40 * u)} size={48 * u} upper ls={0.02} color={theme.ink} />
            </div>
            {rs.length ? <div style={{ ...abs(bw - ptsW, stacked ? 0 : (rowH - 92 * u) / 2) }}>{ptsBlock}</div> : null}
            {rs.length === 0 ? (
              <Txt text="No recent results" w={chipsW} size={28 * u} family="body" color={rgba(theme.ink, 0.6)} align="right" style={abs(chipsX, chipY + chip / 2 - 18 * u)} />
            ) : null}
            {rs.map((r, j) => {
              const s = spring({ frame: frame - at - j * 2, fps, config: CHIP_SPRING });
              if (frame - at - j * 2 < 0) return null;
              const x = chipsRight - (rs.length - j) * chip - (rs.length - 1 - j) * gap;
              const fill = colors[r];
              const latest = j === rs.length - 1;
              return (
                <div
                  key={j}
                  style={{
                    ...abs(x, chipY, chip, chip),
                    transform: `scale(${s})`,
                    background: fill,
                    borderRadius: 12 * u,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: latest ? `0 0 0 ${3 * u}px ${theme.panel}, 0 0 0 ${6 * u}px ${rgba(theme.ink, 0.85)}` : `0 ${4 * u}px ${12 * u}px rgba(0,0,0,0.35)`,
                    fontFamily: TITLE_STACK,
                    fontWeight: 800,
                    fontSize: chip * 0.56,
                    lineHeight: 1,
                    color: readableOn(fill, theme.panel, theme.ink),
                  }}
                >
                  {r}
                </div>
              );
            })}
          </div>
        );
      })}
    </Shell>
  );
};
