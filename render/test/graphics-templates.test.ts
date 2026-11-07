// Every data-graphic template renders (react-dom/server) without throwing for the fixture data and for edge data
// (empty lists, nulls, junk types, long names) in landscape, portrait and square, at several frames; reveal gating is
// visible in the markup; the prediction card always carries its disclaimer.
import { createRequire } from "node:module";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { GRAPHIC_TEMPLATES } from "../src/components/graphics/registry";
import { PREDICTION_DISCLAIMER } from "../src/components/graphics/PredictionCard";
import type { Graphic, RenderProps } from "../src/generated/render_props";
import { readJson, REPO_DIR } from "./helpers";

// Remotion's Img needs a composition around it. Here it is a plain <img>; tests/render/test_graphics.py renders the real one.
vi.mock("remotion", async (original) => ({
  ...(await original<typeof import("remotion")>()),
  Img: (p: React.ImgHTMLAttributes<HTMLImageElement>) => React.createElement("img", p),
}));

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
  "pattern_compare",
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
  pattern_compare: [
    {},
    { home: null, away: "x" },
    { home: { played: 0, ht_ft_sample: 0, btts: { yes: 0, no: 0 }, goal_lines: { "2.5": { over: 0, under: 0 } }, ht_ft: {} }, away: [] },
    { home: { played: "8", btts: "yes", goal_lines: { "2.5": null }, ht_ft_sample: -1, ht_ft: { "W/W": "1", "L/W": Number.NaN } }, away: { played: 3, btts: { yes: 9 } } },
    { title: LONG, home: { played: 1000, btts: { yes: 999 }, goal_lines: { "2.5": { over: 1000 } }, ht_ft_sample: 1000, ht_ft: { "W/W": 500, "W/D": 200, "W/L": 100, "L/W": 300 } }, away: 7 },
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
  it("lineup_board draws the rows from the spec line and y when the props carry them", () => {
    const P = (name: string, position: string, line: number, y: number) => ({ name, number: 1, position, line, y });
    const home = [P("Keeper", "G", 0, 34), P("Rightback", "D", 1, 60), P("Rightcentre", "D", 1, 40), P("Leftcentre", "D", 1, 28), P("Leftback", "D", 1, 8), P("Striker", "M", 2, 34)];
    const html = render(withData("lineup_board", { home, away: [] }), 89);
    const at = ["KEEPER", "LEFTBACK", "LEFTCENTRE", "RIGHTCENTRE", "RIGHTBACK", "STRIKER"].map((n) => html.indexOf(n));
    expect(at.every((i) => i > -1)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });
  it("team_news shows the longest reasons whole at 1920x1080 with six rows", () => {
    const reasons = [
      "Knee, cruciate ligament injury; not expected back before late December",
      "Leg, tibia stress fracture after surgery; expected back in January",
      "Not on the UEFA league-phase list; also recovering from surgery on 11 May (sources name the thigh or hip)",
      "Left out of the squad; reported as rest and workload management (FotMob lists physical discomfort)",
      "Left out of the squad; reported as rest and workload management (FotMob lists physical discomfort)",
      "Hamstring; returned to training and named in the squad, start uncertain",
    ];
    const away = reasons.map((reason, i) => ({ player: `Player ${i}`, reason, status: i === 5 ? "doubt" : "out" }));
    const html = render(withData("team_news", { home: [], away }), 89);
    const text = html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
    for (const r of reasons) expect(text).toContain(r);
    expect(text).not.toContain("…");
  });
  it("scoreline_grid carries the note only when it draws the grid", () => {
    const six = Array.from({ length: 6 }, (_, i) => ({ home: i % 3, away: i % 2, p: 0.1 - i * 0.01 }));
    for (const size of SIZES) {
      expect(render({ ...withData("scoreline_grid", { scorelines: six }), ...size }, 89)).toContain("SIX LIKELIEST SCORES ONLY");
      expect(render({ ...withData("scoreline_grid", { scorelines: six.slice(0, 5) }), ...size }, 89)).not.toContain("LIKELIEST SCORES ONLY");
    }
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

describe("pattern_compare", () => {
  const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const SPLIT = { played: 8, btts: { yes: 4, no: 4 }, goal_lines: { "2.5": { over: 3, under: 5 } }, ht_ft_sample: 7, ht_ft: { "W/W": 2, "W/D": 1, "W/L": 0, "L/W": 0 } };

  it("prints the real report's counts, each team on its own side", () => {
    const t = text(render(fx("pattern_compare"), 75));
    expect(t).toContain("BOTH TEAMS SCORED 5 of 8 3 of 8");
    expect(t).toContain("OVER 2.5 GOALS 5 of 8 2 of 8");
    expect(t).toContain("LED AT HALF-TIME 2 of 8 2 of 8");
    expect(t).toContain("WON FROM BEHIND AT HALF-TIME 0 of 8 0 of 8");
    expect(t).toContain("DROPPED POINTS AFTER LEADING AT HALF-TIME 1 of 8 0 of 8");
  });
  it("brings one row in per reveal", () => {
    const p = fx("pattern_compare"); // reveals 10, 18, 26, 34, 42
    expect(render(p, 9)).not.toContain("BOTH TEAMS SCORED");
    expect(render(p, 10)).toContain("BOTH TEAMS SCORED");
    expect(render(p, 17)).not.toContain("OVER 2.5 GOALS");
    expect(render(p, 18)).toContain("OVER 2.5 GOALS");
    expect(render(p, 41)).not.toContain("DROPPED POINTS");
    expect(render(p, 42)).toContain("DROPPED POINTS");
  });
  it("shows a dash and no bar for a sample of 0 or missing data, and never a percentage", () => {
    for (const away of [null, {}, { played: 0, ht_ft_sample: 0, btts: { yes: 0 }, goal_lines: { "2.5": { over: 0 } }, ht_ft: { "W/W": 0, "W/D": 0, "W/L": 0, "L/W": 0 } }]) {
      for (const size of SIZES) {
        const html = render({ ...withData("pattern_compare", { home: SPLIT, away }), ...size }, 89);
        const t = text(html);
        expect(t).toContain("BOTH TEAMS SCORED 4 of 8 –");
        expect(t).toContain("LED AT HALF-TIME 3 of 7 –");
        expect(t).not.toContain("0 of 0");
        expect(t).not.toContain("%");
        expect(t).not.toContain("…");
      }
    }
  });
  it("keeps a real 0 as a count over an empty track", () => {
    const t = text(render(withData("pattern_compare", { home: SPLIT, away: SPLIT }), 89));
    expect(t).toContain("WON FROM BEHIND AT HALF-TIME 0 of 7 0 of 7");
  });
  it("draws a track only for a known sample", () => {
    const tracks = (html: string) => (html.match(/rgba\(255,255,255,0\.070\)/g) ?? []).length;
    const known = render(withData("pattern_compare", { home: SPLIT, away: SPLIT }), 89);
    const unknown = render(withData("pattern_compare", { home: SPLIT, away: null }), 89);
    expect(tracks(known)).toBe(10);
    expect(tracks(unknown)).toBe(5);
  });
});

describe("text_card bullets", () => {
  const card = (bullets: unknown, size: (typeof SIZES)[number]): RenderProps => {
    const p = { ...fx("stat_compare"), ...size };
    p.graphics = [{ ...p.graphics[0]!, template: "text_card", data: { headline: "The plan", bullets } as Record<string, unknown>, reveals: [] }];
    return p;
  };
  const SENTENCE = "Newcastle press aggressively from a 4-3-3 and force turnovers in the opposition half, then attack the space behind the full-backs quickly.";
  const fontSizes = (html: string) => [...html.matchAll(/font-size:([\d.]+)px/g)].map((m) => Number(m[1]));

  it("keeps full size for short bullets and stays readable with a sentence among them", () => {
    for (const size of SIZES.filter((s) => s.height >= 1080)) {
      const short = render(card(["Press high.", "Sit deep."], size), 45);
      expect(short).toContain("Press high.");
      expect(fontSizes(short)).toContain(34);
      const html = render(card(["Press high.", SENTENCE], size), 45);
      expect(html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ")).toContain(SENTENCE);
      expect(html).not.toContain("…");
      expect(Math.min(...fontSizes(html))).toBeGreaterThanOrEqual(24);
    }
  });
});

describe("crests", () => {
  const PNG = "data:image/png;base64,iVBORw0KGgo=";
  const SVG = "data:image/svg+xml;base64,PHN2Zy8+";
  const withCrests = (p: RenderProps, h: string | null = PNG, a: string | null = SVG): RenderProps => {
    const teams = p.theme.teams;
    return { ...p, theme: { ...p.theme, teams: { H: { ...teams.H, ...(h ? { crest: h } : {}) }, A: { ...teams.A, ...(a ? { crest: a } : {}) } } } };
  };
  const titleGraphic = (p: RenderProps): RenderProps => ({ ...p, graphics: [{ ...p.graphics[0]!, template: "title_card", data: { headline: "Real Madrid v Arsenal", sub: "Preview" }, reveals: [] }] });

  it("appear in the Shell lock-up and on title cards", () => {
    for (const p of [withCrests(fx("stat_compare")), withCrests(titleGraphic(fx("stat_compare")))]) {
      const html = render(p, 75);
      expect(html).toContain(`src="${PNG}"`);
      expect(html).toContain(`src="${SVG}"`);
    }
  });
  it("are nowhere when absent, and the markup is what it was", () => {
    for (const t of M10) expect(render(fx(t), 75)).not.toContain("<img");
    expect(render(titleGraphic(fx("stat_compare")), 75)).not.toContain("<img");
    expect(render(withCrests(fx("stat_compare"), null, null), 75)).toBe(render(fx("stat_compare"), 75));
  });
  it("one missing crest leaves that team its colour block", () => {
    const html = render(withCrests(fx("stat_compare"), PNG, null), 75);
    expect(html.split("<img").length - 1).toBe(1);
  });
  it("never reach for a URL, even if the props carry one", () => {
    for (const url of ["https://example.com/crest.png", "crest.png", "data:image/jpeg;base64,AAAA"]) {
      for (const p of [withCrests(fx("stat_compare"), url, url), withCrests(titleGraphic(fx("stat_compare")), url, url)]) {
        expect(render(p, 75)).not.toContain("<img");
      }
    }
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
