import React from "react";
import type { Theme } from "../../generated/render_props";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { layoutMode, NEWS_REASON_LINES, newsRowLayout, resultColors, revealFrame, revealProgress, shellLayout, wrapText, teamLabel } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asArray, asRecord, pickString, Shell, str, markWidth, TeamMark, Txt, type GraphicProps, type Side } from "./common";

const MAX_ROWS = 6;

interface Absence {
  player: string;
  reason: string;
  status: "out" | "doubt";
}

function absences(v: unknown): Absence[] {
  const out: Absence[] = [];
  for (const x of asArray(v)) {
    const o = asRecord(x);
    const player = str(o.player) || str(o.name);
    if (!player) continue;
    const st = str(o.status).toLowerCase();
    const status = st.startsWith("doubt") || st === "questionable" || st === "50-50" ? "doubt" : "out";
    out.push({ player, reason: str(o.reason), status });
  }
  return out;
}

/** Status icon: out = warn disc with a cross, doubt = accent disc with "?", ok = green disc with a tick. */
const StatusIcon: React.FC<{ kind: "out" | "doubt" | "ok"; size: number; theme: Theme }> = ({ kind, size, theme }) => {
  const fill = kind === "out" ? theme.warn : kind === "doubt" ? theme.accent : resultColors(theme).W;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" style={{ flex: "none" }}>
      <circle cx={20} cy={20} r={19} fill={fill} />
      {kind === "out" ? (
        <path d="M13 13 L27 27 M27 13 L13 27" stroke={theme.ink} strokeWidth={4.5} strokeLinecap="round" />
      ) : kind === "doubt" ? (
        <text x={20} y={29} textAnchor="middle" fontFamily={TITLE_STACK} fontWeight={800} fontSize={27} fill={theme.panel}>
          ?
        </text>
      ) : (
        <path d="M11 21 L18 28 L30 14" stroke={theme.ink} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      )}
    </svg>
  );
};

/** team_news: {home: [{player, reason, status?}], away: [...]} - two columns of absentees, one reveal per team. */
export const TeamNews: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const stacked = mode === "portrait";
  const cols: { side: Side; list: Absence[] }[] = [
    { side: "H", list: absences(d.home) },
    { side: "A", list: absences(d.away) },
  ];
  const shownRows = (list: Absence[]) => (list.length === 0 ? 1 : Math.min(MAX_ROWS, list.length));
  const listedRows = (list: Absence[]) => (list.length > MAX_ROWS ? list.slice(0, MAX_ROWS - 1) : list);
  const headH = 62 * u;
  const gap = (stacked ? 34 : 44) * u;
  const rowsNeeded = stacked ? shownRows(cols[0]!.list) + shownRows(cols[1]!.list) : Math.max(shownRows(cols[0]!.list), shownRows(cols[1]!.list));
  const fixed = stacked ? 2 * (headH + 12 * u) + gap : headH + 12 * u;
  const probe = shellLayout(width, height, { panelW: mode === "landscape" ? 1560 * u : undefined });
  const colW = stacked ? probe.bodyW : (probe.bodyW - gap) / 2;
  const reasons = cols.flatMap(({ list }) => listedRows(list).map((a) => a.reason)).filter(Boolean);
  const { rowH, k, iconS, textX, nameFs, nameLine, reasonW, reasonFs, reasonLine } = newsRowLayout(reasons, colW, (probe.maxBodyH - fixed) / Math.max(1, rowsNeeded), u);
  const L = shellLayout(width, height, { panelW: mode === "landscape" ? 1560 * u : undefined, bodyH: fixed + rowsNeeded * rowH });

  let yCursor = 0;
  return (
    <Shell gp={gp} L={L} kicker="Team news" title={pickString(d, ["title", "headline"]) || "Who's missing"}>
      {cols.map(({ side, list }, ci) => {
        const x = stacked ? 0 : ci * (colW + gap);
        const y = stacked ? yCursor : 0;
        const nRows = shownRows(list);
        yCursor += headH + 12 * u + nRows * rowH + gap;
        const at = revealFrame(g, ci);
        const p = revealProgress(frame, at, 12);
        if (p <= 0) return null;
        const overflow = list.length > MAX_ROWS;
        const rows = listedRows(list);
        const nOut = list.filter((a) => a.status === "out").length;
        const nDoubt = list.length - nOut;
        const summary = list.length === 0 ? "" : [nOut ? `${nOut} out` : "", nDoubt ? `${nDoubt} doubt${nDoubt > 1 ? "s" : ""}` : ""].filter(Boolean).join(" · ");
        const sumW = summary ? 210 * u : 0;
        const pillW = 112 * u;
        const pillH = 36 * u * Math.max(0.8, k);
        const textW = colW - textX - pillW - 20 * u;
        return (
          <div key={side} style={{ ...abs(x, y, colW, headH + 12 * u + nRows * rowH), opacity: clamp01(p * 1.4) }}>
            <div style={{ ...abs(0, 0, colW - sumW, headH), display: "flex", alignItems: "center", gap: 14 * u }}>
              <TeamMark theme={theme} side={side} h={34 * u} u={u} uid={g.id} />
              <Txt text={teamLabel(theme, side, colW - sumW - 26 * u - markWidth(34 * u), 42 * u, 0.03)} w={colW - sumW - 26 * u - markWidth(34 * u)} size={42 * u} upper ls={0.03} color={theme.ink} />
            </div>
            {summary ? (
              <Txt text={summary} w={sumW} size={24 * u} weight={600} ls={0.1} upper color={rgba(theme.ink, 0.6)} align="right" style={abs(colW - sumW, (headH - 29 * u) / 2)} />
            ) : null}
            <div style={{ ...abs(0, headH + 2 * u, colW, Math.max(1, 2 * u)), background: rgba(theme.ink, 0.12) }} />
            {list.length === 0 ? (
              <div style={{ ...abs(0, headH + 12 * u, colW, rowH), display: "flex", alignItems: "center", gap: 18 * u }}>
                <StatusIcon kind="ok" size={iconS} theme={theme} />
                <Txt text="No reported absences" w={colW - iconS - 20 * u} size={30 * u * Math.max(0.8, k)} family="body" weight={500} color={rgba(theme.ink, 0.8)} />
              </div>
            ) : null}
            {rows.map((a, i) => {
              const rp = revealProgress(frame, at + 3 + i * 3, 10);
              if (rp <= 0) return null;
              const ry = headH + 12 * u + i * rowH;
              const tone = a.status === "out" ? theme.warn : theme.accent;
              const reason = wrapText(a.reason, reasonW, reasonFs, NEWS_REASON_LINES).lines;
              const top = (rowH - nameLine - reason.length * reasonLine) / 2;
              return (
                <div key={i} style={{ ...abs(0, ry, colW, rowH), opacity: clamp01(rp * 1.5), transform: `translateX(${(1 - rp) * 20 * u}px)` }}>
                  {i > 0 ? <div style={{ ...abs(textX, 0, colW - textX, Math.max(1, u)), background: rgba(theme.ink, 0.06) }} /> : null}
                  <div style={{ ...abs(0, (rowH - iconS) / 2, iconS, iconS) }}>
                    <StatusIcon kind={a.status} size={iconS} theme={theme} />
                  </div>
                  <Txt text={a.player} w={textW} size={nameFs} min={22 * u * k} family="body" weight={700} color={theme.ink} lh={1.2} style={abs(textX, top)} />
                  {reason.map((line, j) => (
                    <Txt key={j} text={line} w={reasonW} size={reasonFs} min={reasonFs} family="body" weight={500} color={rgba(theme.ink, 0.72)} lh={reasonLine / reasonFs} style={abs(textX, top + nameLine + j * reasonLine)} />
                  ))}
                  <div
                    style={{
                      ...abs(colW - pillW, top + (nameLine - pillH) / 2, pillW, pillH),
                      border: `${Math.max(1, 2 * u)}px solid ${tone}`,
                      borderRadius: 6 * u,
                      boxSizing: "border-box",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontFamily: TITLE_STACK,
                      fontWeight: 800,
                      fontSize: 22 * u * Math.max(0.8, k),
                      letterSpacing: "0.12em",
                      color: tone,
                    }}
                  >
                    {a.status === "out" ? "OUT" : "DOUBT"}
                  </div>
                </div>
              );
            })}
            {overflow ? (
              <div style={{ ...abs(textX, headH + 12 * u + (MAX_ROWS - 1) * rowH, colW - textX, rowH), display: "flex", alignItems: "center" }}>
                <Txt text={`+${list.length - (MAX_ROWS - 1)} more`} w={colW - textX} size={28 * u * k} weight={800} ls={0.08} upper color={rgba(theme.ink, 0.6)} />
              </div>
            ) : null}
          </div>
        );
      })}
    </Shell>
  );
};
