import React from "react";
import type { Theme } from "../../generated/render_props";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { asNumber, cardTeamFill, fitName, kitOutline, layoutMode, revealFrame, revealProgress, shellLayout } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asArray, asRecord, CompareRow, markWidth, Para, paraLines, pickString, Shell, str, TeamMark, Txt, type GraphicProps, type Side } from "./common";

const MAX_STATS = 5;
const JERSEY = "M30 9 L41 4 Q50 13 59 4 L70 9 L93 23 L84 42 L74 36 L74 95 L26 95 L26 36 L16 42 L7 23 Z";

/** Shirt silhouette in team colours with the squad number (no photos). */
const Jersey: React.FC<{ size: number; theme: Theme; side: Side; number: number | null }> = ({ size, theme, side, number }) => {
  const t = theme.teams[side];
  const edge = kitOutline(theme, side);
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
      <path d={JERSEY} fill="#000000" opacity={0.3} transform="translate(1.5 3)" />
      <path d={JERSEY} fill={t.fill} stroke={edge} strokeWidth={2.4} strokeLinejoin="round" />
      <path d="M41 4 Q50 13 59 4" fill="none" stroke={edge} strokeWidth={3.2} />
      {number !== null ? (
        <text x={50} y={74} textAnchor="middle" fontFamily={TITLE_STACK} fontWeight={800} fontSize={number >= 10 ? 38 : 42} fill={t.text}>
          {number}
        </text>
      ) : null}
    </svg>
  );
};

interface Stat {
  label: string;
  value: unknown;
}

function stats(v: unknown): Stat[] {
  return asArray(v)
    .map((x) => {
      const o = asRecord(x);
      return { label: str(o.label), value: o.value ?? null };
    })
    .slice(0, MAX_STATS);
}

/** key_player_duel: {title, home_player:{name, number}, away_player, why?, home_stats[], away_stats[]}. */
export const KeyPlayerDuel: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const hp = asRecord(d.home_player);
  const ap = asRecord(d.away_player);
  const hs = stats(d.home_stats);
  const as = stats(d.away_stats);
  const nStats = Math.max(hs.length, as.length);
  const why = pickString(d, ["why", "note", "reason"]);

  const panelW = mode === "landscape" ? 1560 * u : undefined;
  const bw = shellLayout(width, height, { panelW }).bodyW;
  const whyFs = (mode === "square" ? 26 : 30) * u;
  const whyW = bw - 60 * u;
  const whyLines = paraLines(why, whyW, whyFs, 2);
  const whyLabelH = mode === "square" ? 0 : 30 * u;
  const whyH = why ? whyLabelH + whyLines * whyFs * 1.3 + 4 * u : 0;
  const whyGap = why ? 26 * u : 0;

  // geometry: landscape = [card | VS + stats | card]; otherwise cards (VS between) on top, stats below
  const side = mode === "landscape";
  const ideal = 92 * u;
  const vsH = side ? 96 * u : 0;
  const statsGap = side ? 0 : 28 * u;
  const cardW = side ? 400 * u : (bw - 120 * u) / 2;
  const cardIdeal = side ? 450 * u : mode === "portrait" ? 470 * u : 270 * u;
  const topIdeal = side ? Math.max(cardIdeal, vsH + nStats * ideal) : cardIdeal + statsGap + nStats * ideal;
  const L = shellLayout(width, height, { panelW, bodyH: topIdeal + whyGap + whyH });
  const topH = L.bodyH - whyH - whyGap;
  const cardH = side ? topH : Math.min(cardIdeal, Math.max(200 * u, topH - statsGap - nStats * 60 * u));
  const statsX = side ? cardW + 40 * u : 0;
  const statsW = side ? bw - 2 * cardW - 80 * u : bw;
  const statsH = side ? topH - vsH : topH - cardH - statsGap;
  const rowH = nStats > 0 ? Math.min(ideal, statsH / nStats) : ideal;
  const k = Math.min(1, rowH / ideal);
  const vsY = side ? (topH - vsH - nStats * rowH) / 2 : 0;
  const statsY = side ? vsY + vsH : cardH + statsGap;

  const at0 = revealFrame(g, 0);
  const at1 = revealFrame(g, 1);
  const at2 = revealFrame(g, 2);
  const p0 = revealProgress(frame, at0, 14);
  const p2 = revealProgress(frame, at2, 12);

  const card = (s: Side, player: Record<string, unknown>) => {
    const x = s === "H" ? 0 : bw - cardW;
    const t = theme.teams[s];
    const nameFs = (side || mode === "portrait" ? 46 : 36) * u;
    const teamFs = (side || mode === "portrait" ? 24 : 21) * u;
    const textH = nameFs * 1.2 + teamFs * 1.2;
    const gapJ = 14 * u;
    // jersey takes what the card height leaves after the two text lines (never below 60 px at 1080p)
    const jersey = Math.max(60 * u, Math.min(cardW * 0.66, cardH * 0.6, cardH - 8 * u - textH - gapJ - 28 * u));
    const name = str(player.name);
    const num = asNumber(player.number);
    const shown = name ? fitName(name, cardW - 40 * u, nameFs, "title", 0.02, true) : "–";
    const cardFill = cardTeamFill(theme, s);
    const slide = (1 - p0) * 60 * u * (s === "H" ? -1 : 1);
    const jy = Math.max(0, (cardH - 8 * u - jersey - gapJ - textH) / 2);
    return (
      <div
        key={s}
        style={{
          ...abs(x, 0, cardW, cardH),
          opacity: clamp01(p0 * 1.4),
          transform: `translateX(${slide}px)`,
          borderRadius: 12 * u,
          overflow: "hidden",
          background: `linear-gradient(180deg, ${rgba(cardFill, 0.26)} 0%, ${rgba(cardFill, 0.06)} 70%)`,
          boxShadow: `inset 0 0 0 ${Math.max(1, 2 * u)}px ${rgba(cardFill, 0.35)}`,
        }}
      >
        <div style={{ ...abs(0, 0, cardW, 8 * u), background: cardFill }} />
        <TeamMark theme={theme} side={s} h={26 * u} u={u} uid={g.id} style={abs(s === "H" ? 16 * u : cardW - 16 * u - markWidth(26 * u), 22 * u)} />
        <div style={{ ...abs((cardW - jersey) / 2, jy + 8 * u, jersey, jersey) }}>
          <Jersey size={jersey} theme={theme} side={s} number={num === null ? null : Math.round(num)} />
        </div>
        <Txt text={shown} w={cardW - 40 * u} size={nameFs} upper ls={0.02} color={theme.ink} align="center" style={abs(20 * u, 8 * u + jy + jersey + gapJ)} />
        <Txt text={t.name} w={cardW - 40 * u} size={teamFs} weight={600} ls={0.16} upper color={rgba(theme.ink, 0.6)} align="center" style={abs(20 * u, 8 * u + jy + jersey + gapJ + nameFs * 1.2)} />
      </div>
    );
  };

  const vs = (
    <div
      style={{
        ...(side ? abs(statsX, vsY, statsW, vsH) : abs(cardW, 0, bw - 2 * cardW, cardH)),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: clamp01(p0 * 1.4),
        fontFamily: TITLE_STACK,
        fontWeight: 800,
        fontSize: (side ? 84 : 72) * u,
        lineHeight: 1,
        color: theme.accent,
        letterSpacing: "0.04em",
      }}
    >
      VS
    </div>
  );

  return (
    <Shell gp={gp} L={L} kicker="Key battle" title={pickString(d, ["title", "headline"]) || "The duel"}>
      {p0 > 0 ? card("H", hp) : null}
      {p0 > 0 ? card("A", ap) : null}
      {p0 > 0 ? vs : null}
      {Array.from({ length: nStats }, (_, i) => {
        const p = revealProgress(frame, at1 + i * 3, 14);
        if (p <= 0) return null;
        const h = hs[i];
        const a = as[i];
        const hl = h?.label ?? "";
        const al = a?.label ?? "";
        const label = hl && al && hl.toLowerCase() !== al.toLowerCase() ? `${hl} / ${al}` : hl || al;
        return (
          <CompareRow
            key={i}
            theme={theme}
            u={u}
            x={statsX}
            y={statsY + i * rowH}
            w={statsW}
            h={rowH}
            label={label}
            home={h ? h.value : null}
            away={a ? a.value : null}
            p={p}
            k={k}
            valueW={(side ? 130 : 150) * u}
          />
        );
      })}
      {why && p2 > 0 ? (
        <div style={{ ...abs(0, topH + whyGap, bw, whyH), opacity: clamp01(p2 * 1.4), display: "flex", flexDirection: "column", alignItems: "center" }}>
          {whyLabelH ? (
            <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 22 * u, lineHeight: 1.2, letterSpacing: "0.22em", color: theme.accent, marginBottom: 6 * u }}>WHY IT MATTERS</div>
          ) : null}
          <Para text={why} w={whyW} size={whyFs} color={rgba(theme.ink, 0.88)} lines={2} align="center" />
        </div>
      ) : null}
    </Shell>
  );
};
