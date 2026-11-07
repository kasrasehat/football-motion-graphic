import React from "react";
import { rgba } from "../../lib/colors";
import { layoutMode, lowerBetterFlags, revealFrame, revealProgress, shellLayout } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asArray, asRecord, CompareRow, EmptyNote, pickString, Shell, str, Swatch, Txt, type GraphicProps } from "./common";

const MAX_ROWS = 10;

/** stat_compare: {title?, labels[], home[], away[], units?[], lower_better?[]} - mirrored bars per label, one reveal per row;
 * a lower_better row (rank) gives the smaller value the longer bar. */
export const StatCompare: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const labels = asArray(d.labels);
  const home = asArray(d.home);
  const away = asArray(d.away);
  const units = asArray(d.units);
  const n = Math.min(MAX_ROWS, Math.max(labels.length, home.length, away.length));
  const lowerBetter = lowerBetterFlags(d.lower_better, n);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const panelW = mode === "landscape" ? 1380 * u : undefined;
  const teamRowH = 70 * u;
  const ideal = 92 * u;
  const max = shellLayout(width, height, { panelW });
  const rowH = n > 0 ? Math.min(ideal, (max.maxBodyH - teamRowH) / n) : ideal;
  const L = shellLayout(width, height, { panelW, bodyH: teamRowH + Math.max(1, n) * rowH });
  const bw = L.bodyW;
  const k = Math.min(1, rowH / ideal);
  const valueW = (mode === "landscape" ? 170 : 140) * u;
  const nameW = bw / 2 - 30 * u;
  const teamFs = 40 * u;
  const team = (side: "H" | "A") => (
    <div
      style={{
        ...abs(side === "H" ? 0 : bw / 2 + 30 * u, 0, nameW, teamRowH),
        display: "flex",
        alignItems: "center",
        gap: 14 * u,
        flexDirection: side === "H" ? "row" : "row-reverse",
      }}
    >
      <Swatch theme={theme} side={side} w={14 * u} h={44 * u} u={u} />
      <Txt text={theme.teams[side].name} w={nameW - 30 * u} size={teamFs} upper ls={0.03} color={theme.ink} align={side === "H" ? "left" : "right"} />
    </div>
  );
  return (
    <Shell gp={gp} L={L} kicker="Stat comparison" title={pickString(d, ["title", "headline"]) || "Tale of the tape"}>
      {team("H")}
      {team("A")}
      <div style={{ ...abs(0, teamRowH - 2 * u, bw, Math.max(1, 1.5 * u)), background: rgba(theme.ink, 0.08) }} />
      {n === 0 ? <EmptyNote text="No statistics available" w={bw} h={rowH} u={u} theme={theme} y={teamRowH} /> : null}
      {Array.from({ length: n }, (_, i) => {
        const at = revealFrame(g, i);
        const p = revealProgress(frame, at, 16);
        if (p <= 0) return null;
        return (
          <React.Fragment key={i}>
            {i > 0 ? <div style={{ ...abs(valueW, teamRowH + i * rowH, bw - 2 * valueW, Math.max(1, u)), background: rgba(theme.ink, 0.05) }} /> : null}
            <CompareRow
              theme={theme}
              u={u}
              x={0}
              y={teamRowH + i * rowH}
              w={bw}
              h={rowH}
              label={str(labels[i])}
              home={home[i] ?? null}
              away={away[i] ?? null}
              unit={units[i] ?? null}
              p={p}
              k={k}
              valueW={valueW}
              lowerBetter={lowerBetter[i]}
            />
          </React.Fragment>
        );
      })}
    </Shell>
  );
};
