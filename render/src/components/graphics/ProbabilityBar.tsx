import React from "react";
import { interpolate } from "remotion";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { asNumber, cardTeamFill, cardTrack, largestRemainder, layoutMode, revealFrame, revealProgress, shellLayout, splitEven } from "../../lib/graphics";
import { unit } from "../../lib/layout";
import { abs, asRecord, neutral, pickString, Shell, markWidth, TeamMark, Txt, type GraphicProps, type Side } from "./common";

const GROW_FRAMES = 20;

/** probability_bar: {home, draw, away} (0..1) - one segmented bar; percentages rounded by largest remainder. */
export const ProbabilityBar: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const raw = [d.home, d.draw, d.away].map((v) => {
    const n = asNumber(v);
    return n !== null && n > 0 ? n : 0;
  });
  const sum = raw.reduce((s, x) => s + x, 0);
  const pct = largestRemainder(raw, 100);
  const frac = raw.map((x) => (sum > 0 ? x / sum : 0));
  const big = (mode === "landscape" ? 140 : 120) * u;
  const nameFs = 34 * u;
  const barH = (mode === "landscape" ? 72 : 80) * u;
  const numbersH = big * 1.02 + 10 * u + nameFs * 1.25;
  const bodyH = numbersH + 36 * u + barH + 50 * u;
  const L = shellLayout(width, height, { panelW: mode === "landscape" ? 1400 * u : undefined, bodyH });
  const bw = L.bodyW;
  const barY = numbersH + 36 * u;
  const sepW = 5 * u;
  const colors = [cardTeamFill(theme, "H"), neutral(theme), cardTeamFill(theme, "A")];
  const sides: (Side | null)[] = ["H", null, "A"];
  const labels = [theme.teams.H.name, "Draw", theme.teams.A.name];
  const cols = splitEven(bw, 3, 24 * u);
  let cum = 0;
  return (
    <Shell gp={gp} L={L} kicker="Model probabilities" title={pickString(d, ["title", "headline"]) || `${theme.teams.H.name} v ${theme.teams.A.name}`}>
      <div style={{ ...abs(0, barY, bw, barH), borderRadius: 14 * u, ...cardTrack(theme, u) }} />
      {[0, 1, 2].map((i) => {
        const at = revealFrame(g, i);
        const grow = revealProgress(frame, at, GROW_FRAMES);
        const fade = revealProgress(frame, at, 10);
        const x0 = cum * bw;
        cum += frac[i]!;
        const fullW = frac[i]! * bw;
        const w = Math.max(0, fullW * grow - (i < 2 && frac[i]! > 0 ? sepW / 2 : 0) - (i > 0 && x0 > 0 ? sepW / 2 : 0));
        const segX = x0 + (i > 0 && x0 > 0 ? sepW / 2 : 0);
        const [cx, cw] = cols[i]!;
        const align = i === 0 ? "left" : i === 1 ? "center" : "right";
        const justify = i === 1 ? "center" : "flex-start"; // the away column runs row-reverse, so flex-start is its right edge
        const rise = interpolate(fade, [0, 1], [26 * u, 0]);
        const side = sides[i]!;
        const leftR = i === 0 || x0 <= 0 ? 14 * u : 3 * u;
        const rightR = i === 2 || cum >= 0.9999 ? 14 * u : 3 * u;
        return (
          <React.Fragment key={i}>
            {fade > 0 ? (
              <div style={{ ...abs(cx, 0, cw, numbersH), opacity: clamp01(fade * 1.3), transform: `translateY(${rise}px)` }}>
                <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: big, lineHeight: 1.02, color: theme.ink, textAlign: align, whiteSpace: "nowrap" }}>
                  {sum > 0 ? pct[i] : "–"}
                  <span style={{ fontSize: big * 0.5, color: rgba(theme.ink, 0.75), marginLeft: 4 * u }}>%</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: justify, gap: 12 * u, marginTop: 10 * u, flexDirection: i === 2 ? "row-reverse" : "row" }}>
                  <TeamMark theme={theme} side={side} h={nameFs * 0.8} u={u} uid={g.id} />
                  <Txt text={labels[i]!} w={cw - 12 * u - (side ? markWidth(nameFs * 0.8) : 12 * u) - 6 * u} inline size={nameFs} upper ls={0.04} color={side ? theme.ink : rgba(theme.ink, 0.75)} lh={1.25} />
                </div>
              </div>
            ) : null}
            {w > 0 ? (
              <div
                style={{
                  ...abs(segX, barY, w, barH),
                  background: colors[i],
                  borderRadius: `${leftR}px ${rightR}px ${rightR}px ${leftR}px`,
                  boxShadow: `inset 0 ${-6 * u}px 0 rgba(0,0,0,0.12)`,
                }}
              />
            ) : null}
          </React.Fragment>
        );
      })}
      <div style={{ ...abs(0, barY + barH + 16 * u, bw, 30 * u), display: "flex", justifyContent: "space-between" }}>
        {["0%", "50%", "100%"].map((t) => (
          <div key={t} style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 20 * u, letterSpacing: "0.1em", color: rgba(theme.ink, 0.4) }}>
            {t}
          </div>
        ))}
      </div>
      <div style={{ ...abs(bw / 2 - u, barY - 8 * u, Math.max(1, 2 * u), barH + 16 * u), background: rgba(theme.ink, 0.25) }} />
    </Shell>
  );
};
