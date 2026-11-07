import React from "react";
import type { Graphic, RenderProps } from "../../generated/render_props";
import { BODY_STACK, TITLE_STACK } from "../../fonts";
import { easeOutCubic } from "../../lib/anim";
import { rgba } from "../../lib/colors";
import { fitWrappedSize, wrapText } from "../../lib/graphics";
import { fitFontSize, safeArea, unit } from "../../lib/layout";
import { cardEnvelope, TitleBlock } from "../Cards";
import { pickString, pickStrings, type GraphicProps } from "./common";
import { FormGuide } from "./FormGuide";
import { H2HStrip } from "./H2HStrip";
import { KeyPlayerDuel } from "./KeyPlayerDuel";
import { LineupBoard } from "./LineupBoard";
import { PatternCompare } from "./PatternCompare";
import { PredictionCard } from "./PredictionCard";
import { ProbabilityBar } from "./ProbabilityBar";
import { ScorelineGrid } from "./ScorelineGrid";
import { StatCompare } from "./StatCompare";
import { TeamNews } from "./TeamNews";

export { pickString, pickStrings, type GraphicProps } from "./common";

const TitleCardGraphic: React.FC<GraphicProps> = ({ g, props, frame }) => (
  <TitleBlock
    props={props}
    frame={frame}
    from={g.from}
    to={g.to}
    title={pickString(g.data, ["headline", "title", "heading"])}
    subtitle={pickString(g.data, ["sub", "subtitle", "subheadline", "body", "text"])}
    kicker={pickString(g.data, ["kicker", "eyebrow"]) || undefined}
  />
);

/** Centred panel card: title, optional body line, optional bullets revealed at `reveals[i].frame` (absolute). */
const TextCardGraphic: React.FC<GraphicProps> = ({ g, props, frame }) => {
  const env = cardEnvelope(g.from, g.to, frame, 8, 8);
  if (env <= 0) return null;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const title = pickString(g.data, ["title", "headline", "heading"]).toUpperCase();
  const body = pickString(g.data, ["subtitle", "sub", "body", "text"]);
  const bullets = pickStrings(g.data, ["bullets", "lines", "points", "items"]).slice(0, 6);
  const cardW = (safe.x1 - safe.x0) * (width > height ? 0.62 : 0.94);
  const inner = cardW - 2 * 48 * u;
  const tfs = fitFontSize([title], 76 * u, inner, "title", 0.02);
  const bfs = fitFontSize([body], 36 * u, inner, "body");
  // Fact strings run to a sentence or two: wrap them, rather than shrink the whole list until one long line fits.
  const bulletW = inner - 40 * u;
  const lfs = fitWrappedSize(bullets, bulletW, 34 * u, 24 * u, 3);
  const lift = (1 - easeOutCubic((frame - g.from + 1) / 12)) * 28 * u;
  return (
    <div style={{ position: "absolute", inset: 0, opacity: env, background: rgba("#000000", 0.45) }}>
      <div
        style={{
          position: "absolute",
          left: (width - cardW) / 2,
          width: cardW,
          top: "50%",
          transform: `translateY(calc(-50% + ${lift}px))`,
          background: rgba(theme.panel, 0.95),
          borderTop: `${8 * u}px solid ${theme.accent}`,
          borderRadius: 10 * u,
          padding: `${36 * u}px ${48 * u}px ${40 * u}px`,
          boxSizing: "border-box",
          boxShadow: `0 ${12 * u}px ${40 * u}px rgba(0,0,0,0.45)`,
        }}
      >
        {title ? (
          <div style={{ fontFamily: TITLE_STACK, fontWeight: 800, fontSize: tfs, lineHeight: 1, color: theme.ink, whiteSpace: "nowrap", letterSpacing: "0.02em" }}>
            {title}
          </div>
        ) : null}
        {body ? (
          <div style={{ fontFamily: BODY_STACK, fontWeight: 500, fontSize: bfs, color: rgba(theme.ink, 0.82), marginTop: 14 * u, whiteSpace: "nowrap" }}>{body}</div>
        ) : null}
        {bullets.map((b, i) => {
          const at = g.reveals[i]?.frame ?? g.from;
          if (frame < at) return null;
          const p = easeOutCubic((frame - at + 1) / 8);
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 18 * u,
                marginTop: 18 * u,
                opacity: p,
                transform: `translateX(${(1 - p) * 24 * u}px)`,
                fontFamily: BODY_STACK,
                fontWeight: 500,
                fontSize: lfs,
                color: theme.ink,
                whiteSpace: "nowrap",
              }}
            >
              <div style={{ width: 12 * u, height: 12 * u, borderRadius: 3 * u, background: theme.accent, flex: "none" }} />
              <div>
                {wrapText(b, bulletW, lfs, 3).lines.map((line, n) => (
                  <div key={n}>{line}</div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/**
 * Graphic templates by name. Every template is a pure function of (g, props, frame): it reads `g.data` leniently,
 * gates items on `g.reveals[i].frame` (absolute; see lib/graphics.ts revealFrame) and keeps the caption band clear.
 */
export const GRAPHIC_TEMPLATES: Record<Graphic["template"], React.FC<GraphicProps>> = {
  title_card: TitleCardGraphic,
  text_card: TextCardGraphic,
  stat_compare: StatCompare,
  form_guide: FormGuide,
  h2h_strip: H2HStrip,
  lineup_board: LineupBoard,
  team_news: TeamNews,
  key_player_duel: KeyPlayerDuel,
  probability_bar: ProbabilityBar,
  scoreline_grid: ScorelineGrid,
  prediction_card: PredictionCard,
  pattern_compare: PatternCompare,
};

export const Graphics: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => (
  <>
    {props.graphics.map((g) => {
      if (frame < g.from || frame >= g.to) return null;
      const T = GRAPHIC_TEMPLATES[g.template];
      return T ? <T key={g.id} g={g} props={props} frame={frame} /> : null;
    })}
  </>
);
