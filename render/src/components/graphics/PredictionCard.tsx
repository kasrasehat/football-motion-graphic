import React from "react";
import { TITLE_STACK } from "../../fonts";
import { clamp01 } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { cardTeamFill, cardTeamInk, layoutMode, parseScore, revealFrame, revealProgress, shellLayout } from "../../lib/graphics";
import { estimateTextWidth, unit } from "../../lib/layout";
import { abs, asRecord, neutral, Para, paraLines, pickString, Shell, str, Swatch, Txt, type GraphicProps, type Side } from "./common";

/** Fixed footer of every prediction card (always rendered, whatever the data). */
export const PREDICTION_DISCLAIMER = "Statistical analysis, not betting advice";

const LEVELS = ["low", "medium", "high"] as const;

/** prediction_card: {result: "home"|"draw"|"away", scoreline: "2-1", confidence: "low"|"medium"|"high", note?}. */
export const PredictionCard: React.FC<GraphicProps> = (gp) => {
  const { g, props, frame } = gp;
  const { width, height, theme } = props;
  const d = asRecord(g.data);
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const result = str(d.result).toLowerCase();
  const side: Side | null = result === "home" ? "H" : result === "away" ? "A" : null;
  const isDraw = result === "draw";
  const resultText = side ? `${theme.teams[side].name} win` : isDraw ? "Draw" : "";
  const score = parseScore(d.scoreline);
  const scoreText = score ? null : str(d.scoreline);
  const conf = str(d.confidence).toLowerCase();
  const level = LEVELS.indexOf(conf as (typeof LEVELS)[number]) + 1; // 0 = unknown
  const note = pickString(d, ["note", "text"]);

  const resultFs = (mode === "landscape" ? 84 : 76) * u;
  const scoreFs = (mode === "landscape" ? 196 : 180) * u;
  const chipFs = 48 * u;
  const noteFs = 28 * u;
  const panelW = mode === "landscape" ? 1240 * u : undefined;
  const probe = shellLayout(width, height, { panelW });
  const bw = probe.bodyW;
  const noteLines = paraLines(note, bw - 80 * u, noteFs, 2);
  const resultH = resultFs * 1.1;
  const scoreH = scoreFs * 1.0;
  const confH = 50 * u;
  const footH = 52 * u;
  const yScore = resultH + 22 * u;
  const yConf = yScore + scoreH + 26 * u;
  const yNote = yConf + confH + 20 * u;
  const noteH = note ? noteLines * noteFs * 1.3 : 0;
  const bodyH = yNote + noteH + (note ? 22 * u : 0) + footH;
  const L = shellLayout(width, height, { panelW, bodyH });
  const k = Math.min(1, L.bodyH / bodyH);
  const footY = L.bodyH - footH;

  const p0 = revealProgress(frame, revealFrame(g, 0), 12);
  const p1 = revealProgress(frame, revealFrame(g, 1), 14);
  const p2 = revealProgress(frame, revealFrame(g, 2), 12);

  const chip = (s: Side) => {
    const t = theme.teams[s];
    return (
      <div
        style={{
          background: cardTeamFill(theme, s),
          color: cardTeamInk(theme, s),
          boxShadow: `inset 0 0 0 ${Math.max(1, 2 * u)}px ${rgba(t.ring, 0.6)}`,
          borderRadius: 8 * u,
          padding: `${6 * u}px ${16 * u}px`,
          fontFamily: TITLE_STACK,
          fontWeight: 800,
          fontSize: chipFs * k,
          lineHeight: 1.1,
          letterSpacing: "0.06em",
          whiteSpace: "nowrap",
          flex: "none",
        }}
      >
        {t.short.toUpperCase().slice(0, 4)}
      </div>
    );
  };
  const resultW = estimateTextWidth(resultText.toUpperCase(), resultFs, "title", 0.02);
  const resultMax = bw - 60 * u;
  return (
    <Shell gp={gp} L={L} kicker="The verdict" title={pickString(d, ["title", "headline"]) || "Prediction"}>
      {resultText && p0 > 0 ? (
        <div style={{ ...abs(0, 0, bw, resultH * k), display: "flex", alignItems: "center", justifyContent: "center", gap: 20 * u, opacity: clamp01(p0 * 1.4), transform: `translateY(${(1 - p0) * 20 * u}px)` }}>
          <Swatch theme={theme} side={side} w={14 * u} h={resultFs * 0.78 * k} u={u} style={isDraw ? { background: neutral(theme) } : undefined} />
          <Txt text={resultText} w={Math.min(resultMax, resultW + 4 * u)} size={resultFs * k} upper ls={0.02} color={theme.ink} lh={1.1} inline />
        </div>
      ) : null}
      {p1 > 0 ? (
        <div
          style={{
            ...abs(0, yScore * k, bw, scoreH * k),
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 40 * u,
            opacity: clamp01(p1 * 1.4),
            transform: `scale(${0.9 + 0.1 * p1})`,
          }}
        >
          {chip("H")}
          {score ? (
            <div style={{ display: "flex", alignItems: "center", gap: 26 * u, fontFamily: TITLE_STACK, fontWeight: 800, fontSize: scoreFs * k, lineHeight: 1, color: theme.ink }}>
              <span>{score[0]}</span>
              <span style={{ color: theme.accent, fontSize: scoreFs * k * 0.7 }}>{"–"}</span>
              <span>{score[1]}</span>
            </div>
          ) : (
            <Txt text={scoreText || "–"} w={bw * 0.5} size={scoreFs * k * 0.6} color={theme.ink} align="center" lh={1.05} />
          )}
          {chip("A")}
        </div>
      ) : null}
      {p2 > 0 ? (
        <>
          <div style={{ ...abs(0, yConf * k, bw, confH * k), display: "flex", alignItems: "center", justifyContent: "center", gap: 18 * u, opacity: clamp01(p2 * 1.4) }}>
            <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: 26 * u * k, letterSpacing: "0.2em", color: rgba(theme.ink, 0.62) }}>CONFIDENCE</div>
            <div style={{ display: "flex", gap: 8 * u }}>
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  style={{
                    width: 76 * u * k,
                    height: 16 * u * k,
                    borderRadius: 8 * u,
                    background: i <= level ? theme.accent : rgba(theme.ink, 0.14),
                    opacity: i <= level ? clamp01(p2 * 3 - (i - 1) * 0.6) : 1,
                  }}
                />
              ))}
            </div>
            <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: 34 * u * k, letterSpacing: "0.06em", color: level ? theme.accent : rgba(theme.ink, 0.6), minWidth: 120 * u }}>
              {level ? conf.toUpperCase() : "–"}
            </div>
          </div>
          {note ? (
            <div style={{ ...abs(40 * u, yNote * k, bw - 80 * u, noteH), opacity: clamp01(p2 * 1.4) }}>
              <Para text={note} w={bw - 80 * u} size={noteFs * k} color={rgba(theme.ink, 0.8)} lines={2} align="center" />
            </div>
          ) : null}
        </>
      ) : null}
      <div style={{ ...abs(0, footY, bw, footH), display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end" }}>
        <div style={{ width: bw, height: Math.max(1, 1.5 * u), background: rgba(theme.ink, 0.14), marginBottom: 12 * u }} />
        <Txt text={PREDICTION_DISCLAIMER} w={bw} size={22 * u} min={16 * u} family="body" weight={500} color={rgba(theme.ink, 0.66)} align="center" lh={1.3} />
      </div>
    </Shell>
  );
};
