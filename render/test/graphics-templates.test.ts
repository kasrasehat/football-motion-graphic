// Every data-graphic template renders (react-dom/server) without throwing for the fixture data and for edge data
// (empty lists, nulls, junk types, long names) in landscape, portrait and square, at several frames; reveal gating is
// visible in the markup; the prediction card always carries its disclaimer.
import { createRequire } from "node:module";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import React from "react";
import { describe, expect, it } from "vitest";
import { GRAPHIC_TEMPLATES } from "../src/components/graphics/registry";
import { PREDICTION_DISCLAIMER } from "../src/components/graphics/PredictionCard";
import type { Graphic, RenderProps } from "../src/generated/render_props";
import { readJson, REPO_DIR } from "./helpers";

const { renderToStaticMarkup } = createRequire(import.meta.url)("react-dom/server") as {
  renderToStaticMarkup: (el: React.ReactElement) => string;
};

const M10 = [
  "stat_compare",
  "form_guide",
  "h2h_strip",
  "lineup_board",
  "team_news",
  "key_player_duel",
  "probability_bar",
  "scoreline_grid",
  "prediction_card",
] as const;
type M10Template = (typeof M10)[number];

const SIZES: Pick<RenderProps, "width" | "height" | "orientation">[] = [
  { width: 1920, height: 1080, orientation: "landscape" },
  { width: 1080, height: 1920, orientation: "portrait" },
  { width: 1080, height: 1080, orientation: "square" },
  { width: 960, height: 540, orientation: "landscape" },
];

function fx(t: M10Template): RenderProps {
  return readJson<RenderProps>("tests", "fixtures", "graphics", `${t}.json`);
}

function render(props: RenderProps, frame: number, g: Graphic = props.graphics[0]!): string {
  const T = GRAPHIC_TEMPLATES[g.template];
  return renderToStaticMarkup(React.createElement(T, { g, props, frame }));
}

function withData(t: M10Template, data: unknown, reveals: Graphic["reveals"] | null = null): RenderProps {
  const p = fx(t);
  const g = p.graphics[0]!;
  g.data = data as Record<string, unknown>;
  if (reveals) g.reveals = reveals;
  return p;
}

const LONG = "Maximiliano Bartholomew Fitzgerald-Montgomery de la Cruz Junior";
const longPlayers = (n: number) => Array.from({ length: n }, (_, i) => ({ name: `${LONG} ${i}`, number: i + 1, position: ["G", "D", "D", "D", "D", "M", "M", "M", "F", "F", "F"][i] }));

/** Edge data per template: empty, nulls, junk, and long strings. */
const EDGE: Record<M10Template, unknown[]> = {
  stat_compare: [
    {},
    { labels: [], home: [], away: [] },
    { labels: ["A", "B"], home: [null, "x"], away: [3] },
    { labels: [LONG, 5, null], home: [1e9, -3, Number.NaN], away: [0, 0, 0], units: [LONG, null, "%"] },
    { title: LONG, labels: Array.from({ length: 25 }, (_, i) => `Stat ${i}`), home: Array.from({ length: 25 }, (_, i) => i), away: [] },
    { labels: "nope", home: 4, away: { a: 1 } },
  ],
  form_guide: [{}, { home: [], away: [] }, { home: ["W", null, 3, "x"], away: "WWDLLWWDLWWW" }, { home: Array.from({ length: 30 }, () => "L"), away: null }],
  h2h_strip: [
    {},
    { results: [] },
    { results: [null, 4, { date: "bad", home: LONG, away: LONG, score: "abc" }] },
    { results: Array.from({ length: 12 }, (_, i) => ({ date: `20${10 + i}-01-0${(i % 9) + 1}`, home: i % 2 ? "Arsenal" : "Real Madrid", away: i % 2 ? "Real Madrid" : "Arsenal", score: `${i % 3}-${i % 2}` })) },
    { results: [{ home: "Celtic", away: "Rangers", score: "2-2" }] },
  ],
  lineup_board: [
    {},
    { home: [], away: [] },
    { home: longPlayers(11), away: longPlayers(11), home_formation: "9-9", away_formation: LONG },
    { home: longPlayers(3), away: [{ name: null, number: "x", position: 7 }], home_formation: "4-4-2" },
    { home: Array.from({ length: 16 }, (_, i) => ({ name: `P${i}`, number: i, position: "M" })), away: "junk" },
  ],
  team_news: [
    {},
    { home: [], away: [] },
    { home: Array.from({ length: 14 }, (_, i) => ({ player: `${LONG} ${i}`, reason: LONG, status: i % 2 ? "doubt" : "out" })), away: [{ player: "X" }] },
    { home: [null, { reason: "no name" }, { name: "Alt key", status: "Doubtful" }], away: 5 },
  ],
  key_player_duel: [
    {},
    { title: "", home_player: null, away_player: "x", home_stats: [], away_stats: [] },
    {
      title: LONG,
      home_player: { name: LONG, number: 99 },
      away_player: { name: LONG, number: null },
      why: `${LONG} ${LONG} ${LONG} ${LONG}`,
      home_stats: Array.from({ length: 9 }, (_, i) => ({ label: `${LONG} ${i}`, value: i * 1.234 })),
      away_stats: [{ label: "Other", value: "n/a" }, null],
    },
  ],
  probability_bar: [{}, { home: 0, draw: 0, away: 0 }, { home: null, draw: "0.3", away: -1 }, { home: 0.999, draw: 0.0005, away: 0.0005 }, { home: 1 / 3, draw: 1 / 3, away: 1 / 3 }],
  scoreline_grid: [
    {},
    { scorelines: [] },
    { scorelines: [{ home: 1, away: 1, p: 0.1 }, { home: "x", away: 1 }, null] },
    { scorelines: Array.from({ length: 20 }, (_, i) => ({ home: i % 7, away: (i * 3) % 6, p: i % 4 ? 0.01 * i : null })) },
    { scorelines: Array.from({ length: 6 }, () => ({ home: 9, away: 9, p: 0 })) },
  ],
  prediction_card: [
    {},
    { result: "away", scoreline: "0-3", confidence: "high", note: `${LONG} ${LONG} ${LONG}` },
    { result: "draw", scoreline: "not a score", confidence: "unsure" },
    { result: 7, scoreline: null, confidence: null, note: null },
  ],
};

function assertClean(html: string, where: string): void {
  expect(html, where).not.toMatch(/NaN|undefined|Infinity|\[object Object\]/);
}

describe("graphic registry", () => {
  it("implements every template in the render_props schema", () => {
    const schema = readJson<{ properties: { graphics: { items: { properties: { template: { enum: string[] } } } } } }>("schemas", "artifacts", "render_props.schema.json");
    const names = schema.properties.graphics.items.properties.template.enum;
    for (const n of names) expect(typeof GRAPHIC_TEMPLATES[n as Graphic["template"]], n).toBe("function");
  });
  it("has one fixture per M10 template", () => {
    const files = readdirSync(join(REPO_DIR, "tests", "fixtures", "graphics")).filter((f) => f.endsWith(".json")).sort();
    expect(files).toEqual([...M10].map((t) => `${t}.json`).sort());
  });
});

describe.each(M10)("%s", (t) => {
  it("fixture: covers all frames, pitch hidden, one graphic of this template", () => {
    const p = fx(t);
    expect(p.pitchVisible).toEqual([]);
    expect(p.graphics.length).toBe(1);
    expect(p.graphics[0]).toMatchObject({ template: t, from: 0, to: p.durationInFrames });
    expect(p.graphics[0]!.reveals.length).toBeGreaterThan(0);
  });

  it("renders the fixture in every orientation at every phase", () => {
    for (const size of SIZES) {
      const p = { ...fx(t), ...size };
      const g = p.graphics[0]!;
      for (const frame of [g.from, g.from + 5, ...g.reveals.map((r) => r.frame), 75, g.to - 1]) {
        const html = render(p, frame);
        expect(html.length, `${t} ${size.orientation} @${frame}`).toBeGreaterThan(200);
        assertClean(html, `${t} ${size.orientation} @${frame}`);
      }
      expect(render(p, g.to)).toBe(""); // outside [from, to)
    }
  });

  it("renders edge data (empty, nulls, junk, long names) without throwing", () => {
    for (const [i, data] of EDGE[t].entries()) {
      for (const size of SIZES) {
        for (const reveals of [null, [] as Graphic["reveals"]]) {
          const p = { ...withData(t, data, reveals), ...size };
          for (const frame of [0, 40, 89]) {
            const where = `${t} edge#${i} ${size.orientation} reveals=${reveals ? "none" : "fixture"} @${frame}`;
            const html = render(p, frame);
            expect(html.length, where).toBeGreaterThan(100);
            assertClean(html, where);
          }
        }
      }
    }
  });

  it("is a pure function of (frame, props)", () => {
    const p = fx(t);
    expect(render(p, 37)).toBe(render(fx(t), 37));
  });
});

describe("reveal gating in the markup", () => {
  it("stat_compare: row i appears at reveal i; rows past the last reveal appear with it", () => {
    const p = fx("stat_compare"); // reveals 10, 18, 26, 34; six rows
    expect(render(p, 25)).not.toContain("POSSESSION");
    expect(render(p, 26)).toContain("POSSESSION");
    for (const label of ["CLEAN SHEETS", "LEAGUE POSITION"]) {
      expect(render(p, 33)).not.toContain(label);
      expect(render(p, 34)).toContain(label);
    }
  });
  it("stat_compare without reveals staggers rows from `from`", () => {
    const p = fx("stat_compare");
    p.graphics[0]!.reveals = [];
    expect(render(p, 0)).toContain("GOALS PER GAME");
    expect(render(p, 0)).not.toContain("EXPECTED GOALS");
    expect(render(p, 6)).toContain("EXPECTED GOALS");
    expect(render(p, 30)).toContain("LEAGUE POSITION");
  });
  it("lineup_board: home at R1, away at R2", () => {
    const p = fx("lineup_board"); // 10, 30
    expect(render(p, 29)).toContain("4-3-3");
    expect(render(p, 29)).not.toContain("4-2-3-1");
    expect(render(p, 30)).toContain("4-2-3-1");
  });
  it("h2h_strip lists meetings newest first", () => {
    const html = render(fx("h2h_strip"), 75);
    const i2025 = html.indexOf("16 APR 2025");
    const i2006 = html.indexOf("21 FEB 2006");
    expect(i2025).toBeGreaterThan(-1);
    expect(i2006).toBeGreaterThan(i2025);
  });
  it("probability_bar prints largest-remainder percentages", () => {
    const html = render(fx("probability_bar"), 75);
    for (const n of ["47", "25", "28"]) expect(html).toMatch(new RegExp(`>${n}<`));
  });
  it("form_guide prints points from the results", () => {
    const html = render(fx("form_guide"), 75);
    expect(html).toContain(">10<");
    expect(html).toContain(">13<");
  });
});

describe("prediction_card disclaimer", () => {
  it("is always shown: every frame of the card, every data shape, every orientation", () => {
    for (const data of [fx("prediction_card").graphics[0]!.data, ...EDGE.prediction_card]) {
      for (const size of SIZES) {
        const p = { ...withData("prediction_card", data), ...size };
        for (const frame of [0, 1, 9, 45, 89]) expect(render(p, frame)).toContain(PREDICTION_DISCLAIMER);
      }
    }
  });
  it("names the team, not the side", () => {
    const html = render(fx("prediction_card"), 75);
    expect(html).toContain("REAL MADRID WIN");
    expect(html).toContain("LOW");
  });
});
