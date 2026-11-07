import React from "react";
import type { Theme } from "../../generated/render_props";
import { clamp01, easeOutCubic } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { layoutMode, patternRows, revealFrame, revealProgress, shellLayout, type PatternCell } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asRecord, pickString, Shell, Swatch, Txt, type GraphicProps, type Side } from "./common";

/** One team's half of a row: a bar growing out from the centre over a track that stands for the whole sample. */
const PatternBar: React.FC<{ theme: Theme; side: Side; cell: PatternCell; x: number; y: number; w: number; h: number; grow: number; u: number }> = ({ theme, side, cell, x, y, w, h, grow, u }) => {
  if (!cell) return null; // no sample: no track either, so an unknown can't be read as an empty bar
  const len = w * cell.fraction * grow;
  const { fill, ring } = theme.teams[side];
  return (
    <>
      <div style={{ ...abs(x, y, w, h), background: rgba(theme.ink, 0.07), borderRadius: h / 2 }} />
      {len > 0 ? (
        <div
          style={{
            ...abs(side === "H" ? x + w - len : x, y, len, h),
            background: fill,
            borderRadius: h / 2,
            boxShadow: `inset 0 0 0 ${Math.max(1, 2 * u)}px ${rgba(ring, 0.55)}`,
          }}
        />
      ) : null}
    </>
  );
};

/** pattern_compare: {title?, home, away} split records - five mirrored rows, each a count out of its own sample. */
export const PatternCompare: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const rows = patternRows(d.home, d.away);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const panelW = mode === "landscape" ? 1380 * u : undefined;
  const teamRowH = 70 * u;
  const ideal = 100 * u;
  const max = shellLayout(width, height, { panelW });
  const rowH = Math.min(ideal, (max.maxBodyH - teamRowH) / rows.length);
  const L = shellLayout(width, height, { panelW, bodyH: teamRowH + rows.length * rowH });
  const bw = L.bodyW;
  const k = Math.min(1, rowH / ideal);
  const valueW = (mode === "landscape" ? 170 : 150) * u;
  const nameW = bw / 2 - 30 * u;
  const labelFs = Math.max(20 * u, 28 * u * k);
  const valueFs = Math.max(28 * u, 46 * u * k);
  const barH = Math.max(12 * u, 22 * u * k);
  const gap = 18 * u;
  const centreGap = 8 * u;
  const half = Math.max(0, (bw - 2 * (valueW + gap) - centreGap) / 2);
  const team = (side: Side) => (
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
      <Txt text={theme.teams[side].name} w={nameW - 30 * u} size={40 * u} upper ls={0.03} color={theme.ink} align={side === "H" ? "left" : "right"} />
    </div>
  );
  return (
    <Shell gp={gp} L={L} kicker="Team patterns" title={pickString(d, ["title", "headline"]) || "How their games go"}>
      {team("H")}
      {team("A")}
      <div style={{ ...abs(0, teamRowH - 2 * u, bw, Math.max(1, 1.5 * u)), background: rgba(theme.ink, 0.08) }} />
      {rows.map((row, i) => {
        const p = revealProgress(frame, revealFrame(g, i), 16);
        if (p <= 0) return null;
        const grow = easeOutCubic(p);
        const block = labelFs * 1.2 + 10 * u * k + barH;
        const top = (rowH - block) / 2;
        const barY = top + labelFs * 1.2 + 10 * u * k;
        const valueTop = barY + barH / 2 - valueFs * 0.55;
        const value = (side: Side, cell: PatternCell) => (
          <Txt
            text={cell ? cell.text : "–"}
            w={valueW}
            size={valueFs}
            min={valueFs * 0.6}
            weight={800}
            color={cell ? theme.ink : rgba(theme.ink, 0.55)}
            align={side === "H" ? "right" : "left"}
            lh={1.1}
            style={abs(side === "H" ? 0 : bw - valueW, valueTop)}
          />
        );
        return (
          <div key={row.label} style={{ ...abs(0, teamRowH + i * rowH, bw, rowH), opacity: clamp01(p * 1.6) }}>
            {i > 0 ? <div style={{ ...abs(0, 0, bw, Math.max(1, u)), background: rgba(theme.ink, 0.05) }} /> : null}
            <Txt text={row.label} w={bw} size={labelFs} min={labelFs * 0.75} weight={600} ls={0.06} upper color={rgba(theme.ink, 0.82)} align="center" style={abs(0, top)} />
            <PatternBar theme={theme} side="H" cell={row.home} x={valueW + gap} y={barY} w={half} h={barH} grow={grow} u={u} />
            <PatternBar theme={theme} side="A" cell={row.away} x={valueW + gap + half + centreGap} y={barY} w={half} h={barH} grow={grow} u={u} />
            {value("H", row.home)}
            {value("A", row.away)}
          </div>
        );
      })}
    </Shell>
  );
};
