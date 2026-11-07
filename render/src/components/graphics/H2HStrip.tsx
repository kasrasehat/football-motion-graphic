import React from "react";
import type { Theme } from "../../generated/render_props";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { cardTeamFill, cardTeamInk, formatMatchDay, layoutMode, parseScore, revealFrame, revealProgress, shellLayout, splitEven, teamSide } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asArray, asRecord, EmptyNote, neutral, pickString, Shell, str, Txt, type GraphicProps, type Side } from "./common";

interface Meeting {
  date: string;
  home: string;
  away: string;
  score: [number, number] | null;
  scoreText: string;
  hs: Side | null;
  as: Side | null;
  winner: "home" | "away" | "draw" | null;
}

function meetings(data: Record<string, unknown>, theme: Theme): Meeting[] {
  const out: Meeting[] = [];
  for (const x of asArray(data.results)) {
    const o = asRecord(x);
    const home = str(o.home);
    const away = str(o.away);
    if (!home && !away) continue;
    const score = parseScore(o.score);
    const winner = score === null ? null : score[0] > score[1] ? "home" : score[0] < score[1] ? "away" : "draw";
    out.push({ date: str(o.date), home, away, score, scoreText: str(o.score), hs: teamSide(home, theme), as: teamSide(away, theme), winner });
  }
  // newest first when every row carries an ISO day (stable otherwise: keep the given order)
  if (out.every((m) => /^\d{4}-\d{2}-\d{2}/.test(m.date))) {
    return out.map((m, i) => ({ m, i })).sort((a, b) => (a.m.date < b.m.date ? 1 : a.m.date > b.m.date ? -1 : a.i - b.i)).map((x) => x.m);
  }
  return out;
}

function sideColor(theme: Theme, side: Side | null): string {
  return side ? cardTeamFill(theme, side) : neutral(theme);
}

/** h2h_strip: {results: [{date, home, away, score}]} - recent meetings, newest first, winner highlighted. */
export const H2HStrip: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const all = meetings(d, theme);
  const limit = mode === "landscape" ? 5 : mode === "portrait" ? 6 : 5;
  const ms = all.slice(0, limit);
  const n = ms.length;

  // summary: wins per theme team and draws (only when names can be matched to the theme teams)
  let winsH = 0;
  let winsA = 0;
  let draws = 0;
  let matched = 0;
  for (const m of ms) {
    if (m.hs || m.as) matched++;
    if (m.winner === "draw") draws++;
    else if (m.winner) {
      const w = m.winner === "home" ? m.hs : m.as;
      if (w === "H") winsH++;
      if (w === "A") winsA++;
    }
  }
  const showSummary = matched > 0;
  const summaryH = showSummary ? 92 * u : 0;
  const gapS = showSummary ? 22 * u : 0;
  const tileH = 236 * u;
  const rowH = mode === "portrait" ? 120 * u : 96 * u;
  const rowGap = 14 * u;
  const listH = mode === "landscape" ? tileH : n * rowH + Math.max(0, n - 1) * rowGap;
  const L = shellLayout(width, height, { panelW: mode === "landscape" ? 1560 * u : undefined, bodyH: summaryH + gapS + Math.max(listH, 120 * u) });
  const bw = L.bodyW;
  const k = Math.min(1, L.bodyH / (summaryH + gapS + Math.max(listH, 120 * u)));
  const listY = summaryH + gapS;
  const rH = rowH * k;
  const rGap = rowGap * k;

  const summary = showSummary ? (
    <div style={{ ...abs(0, 0, bw, summaryH), opacity: clamp01(revealProgress(frame, g.from, 10) * 1.4) }}>
      {splitEven(bw, 3, 18 * u).map(([x, w], i) => {
        const side: Side | null = i === 0 ? "H" : i === 2 ? "A" : null;
        const count = i === 0 ? winsH : i === 1 ? draws : winsA;
        const label = side ? `${mode === "landscape" ? theme.teams[side].name : theme.teams[side].short} wins` : draws === 1 ? "Draw" : "Draws";
        const align = i === 1 ? "center" : "flex-start"; // the away block runs row-reverse
        return (
          <div key={i} style={{ ...abs(x, 0, w, summaryH), background: rgba(theme.ink, 0.05), borderRadius: 10 * u, overflow: "hidden" }}>
            <div style={{ ...abs(i === 2 ? w - 8 * u : 0, 0, 8 * u, summaryH), background: sideColor(theme, side) }} />
            <div style={{ ...abs(26 * u, 0, w - 52 * u, summaryH), display: "flex", alignItems: "center", justifyContent: align, gap: 18 * u, flexDirection: i === 2 ? "row-reverse" : "row" }}>
              <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: 60 * u, lineHeight: 1, color: theme.ink }}>{count}</div>
              <Txt text={label} w={w - 52 * u - 70 * u} inline size={26 * u} family="title" weight={600} ls={0.1} upper color={rgba(theme.ink, 0.72)} />
            </div>
          </div>
        );
      })}
    </div>
  ) : null;

  const winnerSide = (m: Meeting): Side | null => (m.winner === "home" ? m.hs : m.winner === "away" ? m.as : null);
  const accentFor = (m: Meeting): string => (m.winner === "draw" || m.winner === null ? neutral(theme) : sideColor(theme, winnerSide(m)));

  const tiles =
    mode === "landscape"
      ? (() => {
          const tw = Math.min(330 * u, (bw - (n - 1) * 20 * u) / Math.max(1, n));
          const total = n * tw + (n - 1) * 20 * u;
          const x0 = (bw - total) / 2;
          return ms.map((m, i) => {
            const at = revealFrame(g, i);
            const p = revealProgress(frame, at, 12);
            if (p <= 0) return null;
            const x = x0 + i * (tw + 20 * u);
            const day = formatMatchDay(m.date);
            const scoreW = 56 * u;
            const nameW = tw - 22 * u - 8 * u - 14 * u - scoreW - 18 * u;
            const line = (name: string, goals: number | null, side: Side | null, isWinner: boolean, j: number) => {
              const dim = m.winner === "home" || m.winner === "away" ? (isWinner ? 1 : 0.45) : 0.9;
              return (
                <div style={{ ...abs(22 * u, 72 * u + j * 62 * u, tw - 40 * u, 52 * u), display: "flex", alignItems: "center", gap: 14 * u, opacity: dim }}>
                  <div style={{ width: 8 * u, height: 44 * u, borderRadius: 4 * u, background: sideColor(theme, side), flex: "none" }} />
                  <Txt text={name} w={nameW} size={34 * u} upper ls={0.02} color={theme.ink} />
                  <div style={{ width: scoreW, textAlign: "right", fontFamily: TITLE_STACK, fontWeight: 800, fontSize: 50 * u, lineHeight: 1, color: theme.ink }}>
                    {goals === null ? "" : goals}
                  </div>
                </div>
              );
            };
            const tag = m.winner === "draw" ? "Draw" : m.winner ? `${m.winner === "home" ? m.home : m.away} win` : m.scoreText;
            const tagSide = winnerSide(m);
            const tagFill = m.winner === "draw" || !m.winner ? rgba(theme.ink, 0.12) : sideColor(theme, tagSide);
            const tagInk = tagSide && tagFill === sideColor(theme, tagSide) ? cardTeamInk(theme, tagSide) : theme.ink;
            return (
              <div
                key={i}
                style={{
                  ...abs(x, listY, tw, tileH),
                  opacity: clamp01(p * 1.5),
                  transform: `translateY(${(1 - p) * 24 * u}px)`,
                  background: rgba(theme.ink, 0.05),
                  borderRadius: 10 * u,
                  overflow: "hidden",
                }}
              >
                <div style={{ ...abs(0, 0, tw, 6 * u), background: accentFor(m) }} />
                <Txt text={day.full || "–"} w={tw - 44 * u} size={24 * u} family="title" weight={600} ls={0.12} upper color={rgba(theme.ink, 0.62)} style={abs(22 * u, 24 * u)} />
                {line(m.home, m.score ? m.score[0] : null, m.hs, m.winner === "home", 0)}
                {line(m.away, m.score ? m.score[1] : null, m.as, m.winner === "away", 1)}
                <div style={{ ...abs(22 * u, 192 * u, tw - 44 * u, 34 * u), display: "flex", alignItems: "center" }}>
                  <div style={{ background: tagFill, borderRadius: 6 * u, padding: `${3 * u}px ${12 * u}px`, maxWidth: tw - 44 * u, boxSizing: "border-box" }}>
                    <Txt text={tag} w={tw - 68 * u} inline size={22 * u} family="title" weight={800} ls={0.08} upper color={tagInk} lh={1.15} />
                  </div>
                </div>
              </div>
            );
          });
        })()
      : ms.map((m, i) => {
          const at = revealFrame(g, i);
          const p = revealProgress(frame, at, 12);
          if (p <= 0) return null;
          const y = listY + i * (rH + rGap);
          const day = formatMatchDay(m.date);
          const dateW = 128 * u;
          const scoreBoxW = 150 * u;
          const restX = dateW + 18 * u;
          const restW = bw - restX - 16 * u;
          const cx = restX + restW / 2;
          const nameW = restW / 2 - scoreBoxW / 2 - 30 * u;
          const nameFs = 36 * u * Math.min(1, k * 1.05);
          const hw = m.winner === "home";
          const aw = m.winner === "away";
          const decided = hw || aw;
          return (
            <div
              key={i}
              style={{
                ...abs(0, y, bw, rH),
                opacity: clamp01(p * 1.5),
                transform: `translateX(${(1 - p) * 30 * u}px)`,
                background: rgba(theme.ink, 0.05),
                borderRadius: 10 * u,
                overflow: "hidden",
              }}
            >
              <div style={{ ...abs(0, 0, 6 * u, rH), background: accentFor(m) }} />
              <div style={{ ...abs(20 * u, 0, dateW, rH), display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <Txt text={day.day || "–"} w={dateW - 8 * u} size={30 * u} family="title" weight={800} upper color={theme.ink} lh={1.05} />
                {day.year ? <Txt text={day.year} w={dateW - 8 * u} size={22 * u} family="title" weight={600} ls={0.1} color={rgba(theme.ink, 0.55)} lh={1.1} /> : null}
              </div>
              <div style={{ ...abs(cx - scoreBoxW / 2 - 30 * u - nameW, 0, nameW + 22 * u, rH), display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12 * u, opacity: decided && !hw ? 0.5 : 1 }}>
                <Txt text={m.home} w={nameW - 12 * u} size={nameFs} upper ls={0.02} color={theme.ink} align="right" />
                <div style={{ width: 8 * u, height: rH * 0.46, borderRadius: 4 * u, background: sideColor(theme, m.hs), flex: "none" }} />
              </div>
              <div
                style={{
                  ...abs(cx - scoreBoxW / 2, (rH - 64 * u * k) / 2, scoreBoxW, 64 * u * k),
                  background: rgba(theme.ink, 0.1),
                  borderRadius: 8 * u,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 10 * u,
                  fontFamily: TITLE_STACK,
                  fontWeight: 800,
                  fontSize: 46 * u * k,
                  lineHeight: 1,
                  color: theme.ink,
                }}
              >
                {m.score ? (
                  <>
                    <span style={{ opacity: decided && !hw ? 0.55 : 1 }}>{m.score[0]}</span>
                    <span style={{ opacity: 0.5 }}>{"–"}</span>
                    <span style={{ opacity: decided && !aw ? 0.55 : 1 }}>{m.score[1]}</span>
                  </>
                ) : (
                  <Txt text={m.scoreText || "–"} w={scoreBoxW - 16 * u} size={40 * u * k} align="center" color={theme.ink} />
                )}
              </div>
              <div style={{ ...abs(cx + scoreBoxW / 2 + 8 * u, 0, nameW + 22 * u, rH), display: "flex", alignItems: "center", gap: 12 * u, opacity: decided && !aw ? 0.5 : 1 }}>
                <div style={{ width: 8 * u, height: rH * 0.46, borderRadius: 4 * u, background: sideColor(theme, m.as), flex: "none" }} />
                <Txt text={m.away} w={nameW - 12 * u} size={nameFs} upper ls={0.02} color={theme.ink} />
              </div>
            </div>
          );
        });

  return (
    <Shell gp={gp} L={L} kicker="Head to head" title={pickString(d, ["title", "headline"]) || "Recent meetings"}>
      {summary}
      {n === 0 ? <EmptyNote text="No recent meetings" w={bw} h={120 * u} u={u} theme={theme} y={listY} /> : tiles}
    </Shell>
  );
};
