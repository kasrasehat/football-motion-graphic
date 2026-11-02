import React from "react";
import type { Theme } from "../../generated/render_props";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { mix, readableOn, rgba } from "../../lib/colors";
import { asNumber, layoutMode, percentText, revealFrame, revealProgress, shellLayout } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asArray, asRecord, EmptyNote, neutral, pickString, Shell, Txt, type GraphicProps } from "./common";

const GRID_N = 5; // 0..4 goals each way
const GRID_MIN_ENTRIES = 6;

interface Scoreline {
  home: number;
  away: number;
  p: number | null;
}

function scorelines(v: unknown): Scoreline[] {
  const out: { s: Scoreline; i: number }[] = [];
  asArray(v).forEach((x, i) => {
    const o = asRecord(x);
    const h = asNumber(o.home);
    const a = asNumber(o.away);
    if (h === null || a === null || h < 0 || a < 0) return;
    out.push({ s: { home: Math.round(h), away: Math.round(a), p: asNumber(o.p) }, i });
  });
  return out.sort((a, b) => (b.s.p ?? -1) - (a.s.p ?? -1) || a.i - b.i).map((x) => x.s);
}

function outcome(theme: Theme, s: Scoreline): { label: string; color: string } {
  if (s.home > s.away) return { label: `${theme.teams.H.short} win`, color: theme.teams.H.fill };
  if (s.away > s.home) return { label: `${theme.teams.A.short} win`, color: theme.teams.A.fill };
  return { label: "Draw", color: neutral(theme) };
}

interface TileProps {
  theme: Theme;
  u: number;
  s: Scoreline;
  rank: number;
  maxP: number;
  x: number;
  y: number;
  w: number;
  h: number;
  p: number;
}

/** Ranked scoreline tile; horizontal layout when wide, stacked when narrow. */
const Tile: React.FC<TileProps> = ({ theme, u, s, rank, maxP, x, y, w, h, p }) => {
  const o = outcome(theme, s);
  const wide = w / h >= 1.9;
  const scoreFs = Math.min(wide ? h * 0.56 : h * 0.4, 84 * u);
  const probFs = Math.min(wide ? h * 0.3 : h * 0.2, 40 * u);
  const badge = Math.min(46 * u, h * 0.36);
  const share = maxP > 0 && s.p !== null ? clamp01(s.p / maxP) : 0;
  const top = rank === 1;
  const score = `${s.home}–${s.away}`;
  return (
    <div
      style={{
        ...abs(x, y, w, h),
        opacity: clamp01(p * 1.5),
        transform: `translateY(${(1 - p) * 20 * u}px)`,
        background: top ? rgba(theme.accent, 0.1) : rgba(theme.ink, 0.05),
        boxShadow: `inset 0 0 0 ${Math.max(1, (top ? 2.5 : 1.5) * u)}px ${top ? theme.accent : rgba(theme.ink, 0.1)}`,
        borderRadius: 10 * u,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          ...abs(14 * u, wide ? (h - 6 * u - badge) / 2 : 14 * u, badge, badge),
          borderRadius: "50%",
          background: top ? theme.accent : rgba(theme.ink, 0.14),
          color: top ? theme.panel : theme.ink,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: TITLE_STACK,
          fontWeight: 800,
          fontSize: badge * 0.56,
        }}
      >
        {rank}
      </div>
      {wide ? (
        <>
          <Txt text={score} w={w * 0.4} size={scoreFs} color={theme.ink} align="center" lh={1.05} style={abs(badge + 24 * u, (h - 6 * u - scoreFs * 1.05) / 2)} />
          <div style={{ ...abs(w * 0.4 + badge + 30 * u, 0, w - (w * 0.4 + badge + 30 * u) - 18 * u, h - 6 * u), display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "flex-end" }}>
            <Txt text={percentText(s.p)} w={w * 0.4} size={probFs} color={theme.accent} align="right" lh={1.1} />
            <Txt text={o.label} w={w * 0.4} size={Math.max(16 * u, probFs * 0.55)} weight={600} ls={0.1} upper color={rgba(theme.ink, 0.6)} align="right" lh={1.2} />
          </div>
        </>
      ) : (
        <>
          <Txt text={score} w={w - 24 * u} size={scoreFs} color={theme.ink} align="center" lh={1.05} style={abs(12 * u, h * 0.2)} />
          <Txt text={percentText(s.p)} w={w - 24 * u} size={probFs} color={theme.accent} align="center" lh={1.1} style={abs(12 * u, h * 0.2 + scoreFs * 1.08)} />
          <Txt text={o.label} w={w - 24 * u} size={Math.max(16 * u, probFs * 0.6)} weight={600} ls={0.1} upper color={rgba(theme.ink, 0.6)} align="center" lh={1.2} style={abs(12 * u, h * 0.2 + scoreFs * 1.08 + probFs * 1.15)} />
        </>
      )}
      <div style={{ ...abs(0, h - 6 * u, w, 6 * u), background: rgba(theme.ink, 0.08) }} />
      <div style={{ ...abs(0, h - 6 * u, w * share * clamp01(p), 6 * u), background: o.color }} />
    </div>
  );
};

/** 0-4 x 0-4 probability heat grid (home goals down, away goals across). */
const HeatGrid: React.FC<{ theme: Theme; u: number; list: Scoreline[]; size: number; x: number; y: number; frame: number; at: number }> = ({
  theme,
  u,
  list,
  size,
  x,
  y,
  frame,
  at,
}) => {
  const band = 34 * u;
  const cs = (size - band) / (GRID_N + 0.6);
  const head = cs * 0.6;
  const cells = new Map<string, number>();
  for (const s of list) {
    if (s.home < GRID_N && s.away < GRID_N && s.p !== null && !cells.has(`${s.home}-${s.away}`)) cells.set(`${s.home}-${s.away}`, s.p);
  }
  const maxP = Math.max(0, ...cells.values());
  const gx = band + head;
  const gy = band + head;
  const label: React.CSSProperties = { fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 20 * u, letterSpacing: "0.14em", color: rgba(theme.ink, 0.6), whiteSpace: "nowrap" };
  return (
    <div style={{ ...abs(x, y, size, size) }}>
      <div style={{ ...abs(gx, 0, cs * GRID_N, band), display: "flex", alignItems: "center", justifyContent: "center", ...label }}>
        <span style={{ maxWidth: cs * GRID_N, overflow: "hidden", textOverflow: "ellipsis" }}>{`${theme.teams.A.short.toUpperCase()} GOALS`}</span>
      </div>
      <div style={{ ...abs(0, gy, band, cs * GRID_N), display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ ...label, transform: "rotate(-90deg)" }}>{`${theme.teams.H.short.toUpperCase()} GOALS`}</div>
      </div>
      {Array.from({ length: GRID_N }, (_, i) => (
        <React.Fragment key={`h${i}`}>
          <div style={{ ...abs(gx + i * cs, band, cs, head), display: "flex", alignItems: "center", justifyContent: "center", fontFamily: TITLE_STACK, fontWeight: 800, fontSize: Math.min(28 * u, head * 0.7), color: rgba(theme.ink, 0.8) }}>{i}</div>
          <div style={{ ...abs(band, gy + i * cs, head, cs), display: "flex", alignItems: "center", justifyContent: "center", fontFamily: TITLE_STACK, fontWeight: 800, fontSize: Math.min(28 * u, head * 0.7), color: rgba(theme.ink, 0.8) }}>{i}</div>
        </React.Fragment>
      ))}
      {Array.from({ length: GRID_N * GRID_N }, (_, k) => {
        const r = Math.floor(k / GRID_N);
        const c = k % GRID_N;
        const p = cells.get(`${r}-${c}`);
        const t = p !== undefined && maxP > 0 ? Math.pow(clamp01(p / maxP), 0.75) : 0;
        const fade = revealProgress(frame, at + r + c, 10);
        const bg = p !== undefined ? mix(mix(theme.panel, theme.ink, 0.08), theme.accent, 0.12 + 0.88 * t) : mix(theme.panel, theme.ink, 0.04);
        const isMax = p !== undefined && p === maxP && maxP > 0;
        const txt = p === undefined ? "" : percentText(p);
        return (
          <div
            key={k}
            style={{
              ...abs(gx + c * cs + 2 * u, gy + r * cs + 2 * u, cs - 4 * u, cs - 4 * u),
              opacity: fade,
              background: bg,
              borderRadius: 6 * u,
              boxShadow: isMax ? `inset 0 0 0 ${Math.max(1, 3 * u)}px ${theme.ink}` : undefined,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: TITLE_STACK,
              fontWeight: 800,
              fontSize: Math.min(26 * u, cs * 0.27),
              color: readableOn(bg, theme.panel, theme.ink),
              whiteSpace: "nowrap",
              overflow: "hidden",
            }}
          >
            {txt}
          </div>
        );
      })}
    </div>
  );
};

/** scoreline_grid: {scorelines: [{home, away, p}]} - ranked tiles (+ a 0-4 heat grid when there are >= 6 entries). */
export const ScorelineGrid: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const list = scorelines(d.scorelines);
  const grid = list.length >= GRID_MIN_ENTRIES;
  const maxP = Math.max(0, ...list.map((s) => s.p ?? 0));
  const gap = 18 * u;

  const probe = shellLayout(width, height, { panelW: mode === "landscape" ? 1560 * u : undefined });
  const bw = probe.bodyW;
  let tiles: { x: number; y: number; w: number; h: number }[] = [];
  let gridBox: { x: number; y: number; s: number } | null = null;
  let bodyH: number;
  if (grid) {
    const shown = 6;
    if (mode === "landscape") {
      const gs = Math.min(probe.maxBodyH, 540 * u);
      const tw = bw - gs - 48 * u;
      const th = (gs - 2 * gap) / 3;
      const cw = (tw - gap) / 2;
      tiles = Array.from({ length: shown }, (_, i) => ({ x: (i % 2) * (cw + gap), y: Math.floor(i / 2) * (th + gap), w: cw, h: th }));
      gridBox = { x: bw - gs, y: 0, s: gs };
      bodyH = gs;
    } else if (mode === "portrait") {
      const th = 136 * u;
      const cw = (bw - gap) / 2;
      tiles = Array.from({ length: shown }, (_, i) => ({ x: (i % 2) * (cw + gap), y: Math.floor(i / 2) * (th + gap), w: cw, h: th }));
      const ty = 3 * th + 2 * gap + 36 * u;
      const gs = Math.min(bw * 0.8, probe.maxBodyH - ty);
      gridBox = { x: (bw - gs) / 2, y: ty, s: gs };
      bodyH = ty + gs;
    } else {
      // square: a full-height column of 6 tiles, the grid beside it (vertically centred)
      bodyH = probe.maxBodyH;
      const gs = Math.min(bodyH, bw * 0.44);
      const tw = bw - gs - 32 * u;
      const tg = 12 * u;
      const th = (bodyH - 5 * tg) / 6;
      tiles = Array.from({ length: shown }, (_, i) => ({ x: 0, y: i * (th + tg), w: tw, h: th }));
      gridBox = { x: bw - gs, y: (bodyH - gs) / 2, s: gs };
    }
  } else {
    const n = Math.min(5, list.length);
    if (mode === "landscape") {
      const tw = Math.min(300 * u, (bw - (n - 1) * gap) / Math.max(1, n));
      const x0 = (bw - (n * tw + (n - 1) * gap)) / 2;
      tiles = Array.from({ length: n }, (_, i) => ({ x: x0 + i * (tw + gap), y: 0, w: tw, h: 250 * u }));
      bodyH = 250 * u;
    } else {
      const th = Math.min(120 * u, (probe.maxBodyH - (n - 1) * gap) / Math.max(1, n));
      tiles = Array.from({ length: n }, (_, i) => ({ x: 0, y: i * (th + gap), w: bw, h: th }));
      bodyH = Math.max(120 * u, n * th + (n - 1) * gap);
    }
  }
  const L = shellLayout(width, height, { panelW: mode === "landscape" ? 1560 * u : undefined, bodyH });
  return (
    <Shell gp={gp} L={L} kicker="Scorelines" title={pickString(d, ["title", "headline"]) || "Most likely results"}>
      {list.length === 0 ? <EmptyNote text="No scorelines available" w={L.bodyW} h={120 * u} u={u} theme={theme} /> : null}
      {tiles.map((t, i) => {
        const s = list[i];
        if (!s) return null;
        const p = revealProgress(frame, revealFrame(g, i), 12);
        if (p <= 0) return null;
        return <Tile key={i} theme={theme} u={u} s={s} rank={i + 1} maxP={maxP} x={t.x} y={t.y} w={t.w} h={t.h} p={p} />;
      })}
      {gridBox ? <HeatGrid theme={theme} u={u} list={list} size={gridBox.s} x={gridBox.x} y={gridBox.y} frame={frame} at={revealFrame(g, 0)} /> : null}
    </Shell>
  );
};
