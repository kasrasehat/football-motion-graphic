// Team colours on the dark data cards: a fill that would vanish into the card (e.g. Aston Villa's #101820) is
// swapped for the secondary or a lightened variant, the empty track stays distinct, "lower is better" rows (league
// position) give the better rank the longer bar, and the scene-title chip never sits on a graphic card.
import { createRequire } from "node:module";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { GRAPHIC_TEMPLATES } from "../src/components/graphics/registry";
import type { Graphic, RenderProps, Theme } from "../src/generated/render_props";
import { contrastRatio, hexToHsl } from "../src/lib/colors";
import {
  CARD_FILL_MIN_CONTRAST,
  cardSurface,
  cardTeamFill,
  cardTeamInk,
  contrastSafeFill,
  kitOutline,
  lowerBetterFlags,
  ordinal,
  rankFractions,
} from "../src/lib/graphics";
import { hudRects, sceneTitleLayout } from "../src/lib/hud";
import { fixture, readJson } from "./helpers";

vi.mock("remotion", async (original) => ({
  ...(await original<typeof import("remotion")>()),
  Img: (p: React.ImgHTMLAttributes<HTMLImageElement>) => React.createElement("img", p),
}));

const { renderToStaticMarkup } = createRequire(import.meta.url)("react-dom/server") as {
  renderToStaticMarkup: (el: React.ReactElement) => string;
};

const VILLA = { fill: "#101820", ring: "#f2c230", text: "#ffffff", short: "AVL", name: "Aston Villa" };
const UNITED = { fill: "#da291c", ring: "#ffffff", text: "#ffffff", short: "MUN", name: "Manchester United" };

function graphicProps(template: string, data: Record<string, unknown>, size: Partial<RenderProps> = {}): RenderProps {
  const p = readJson<RenderProps>("tests", "fixtures", "graphics", `${template}.json`);
  p.theme.teams.H = { ...UNITED };
  p.theme.teams.A = { ...VILLA };
  p.graphics[0]!.data = data;
  return { ...p, ...size };
}

function render(p: RenderProps, frame = 89): string {
  const g: Graphic = p.graphics[0]!;
  return renderToStaticMarkup(React.createElement(GRAPHIC_TEMPLATES[g.template], { g, props: p, frame }));
}

describe("contrast-safe team fills", () => {
  const theme = (): Theme => ({ ...fixture().theme, teams: { H: { ...UNITED }, A: { ...VILLA } } });
  it("keeps a primary that already reads on the card", () => {
    expect(cardTeamFill(theme(), "H")).toBe(UNITED.fill);
    expect(cardTeamInk(theme(), "H")).toBe(UNITED.text);
  });
  it("swaps a dark primary for the secondary when that reads (Villa navy -> gold)", () => {
    const bg = cardSurface(theme());
    expect(contrastRatio(VILLA.fill, bg)).toBeLessThan(CARD_FILL_MIN_CONTRAST);
    expect(cardTeamFill(theme(), "A")).toBe(VILLA.ring);
    expect(contrastRatio(cardTeamFill(theme(), "A"), bg)).toBeGreaterThanOrEqual(CARD_FILL_MIN_CONTRAST);
    expect(contrastRatio(cardTeamInk(theme(), "A"), cardTeamFill(theme(), "A"))).toBeGreaterThanOrEqual(4.5);
  });
  it("lightens the primary, keeping its hue, when the secondary is dark too", () => {
    const bg = "#0e1d15";
    const c = contrastSafeFill("#101860", "#000000", bg);
    expect(contrastRatio(c, bg)).toBeGreaterThanOrEqual(CARD_FILL_MIN_CONTRAST);
    expect(Math.abs(hexToHsl(c)[0] - hexToHsl("#101860")[0])).toBeLessThan(6);
  });
  it("darkens instead on a light card", () => {
    const c = contrastSafeFill("#f4f4f4", "#ffffee", "#ffffff");
    expect(contrastRatio(c, "#ffffff")).toBeGreaterThanOrEqual(CARD_FILL_MIN_CONTRAST);
  });
  it("is always >= 3:1 for a sweep of kits on the card", () => {
    const bg = cardSurface(theme());
    for (let r = 0; r < 256; r += 51)
      for (let g = 0; g < 256; g += 51)
        for (let b = 0; b < 256; b += 51) {
          const hex = `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
          expect(contrastRatio(contrastSafeFill(hex, "#0a0a0a", bg), bg), hex).toBeGreaterThanOrEqual(CARD_FILL_MIN_CONTRAST);
        }
  });
  it("outlines a kit whose fill and ring both vanish", () => {
    const t = theme();
    expect(kitOutline(t, "A")).toBe(VILLA.ring);
    t.teams.A = { ...VILLA, ring: "#0a0a0a" };
    expect(kitOutline(t, "A")).toMatch(/^rgba\(255,255,255/);
  });
});

describe("templates draw the safe fill, never the vanishing one", () => {
  const SIZES: Partial<RenderProps>[] = [
    { width: 1920, height: 1080, orientation: "landscape" },
    { width: 1080, height: 1920, orientation: "portrait" },
    { width: 1080, height: 1080, orientation: "square" },
  ];
  const DATA: Record<string, Record<string, unknown>> = {
    probability_bar: { home: 0.45, draw: 0.26, away: 0.29 },
    stat_compare: { labels: ["Points", "Goals"], home: [7, 11], away: [12, 14] },
    pattern_compare: {
      home: { played: 4, btts: { yes: 2 }, goal_lines: { "2.5": { over: 2 } }, ht_ft_sample: 4, ht_ft: { "W/W": 1, "W/D": 0, "W/L": 0, "L/W": 0 } },
      away: { played: 4, btts: { yes: 3 }, goal_lines: { "2.5": { over: 3 } }, ht_ft_sample: 4, ht_ft: { "W/W": 2, "W/D": 1, "W/L": 0, "L/W": 1 } },
    },
    form_guide: { home: ["D", "L"], away: ["W", "W"] },
    team_news: { home: [{ player: "A", reason: "knee", status: "out" }], away: [{ player: "B", reason: "ban", status: "out" }] },
    h2h_strip: { results: [{ date: "2025-01-01", home: "Aston Villa", away: "Manchester United", score: "2-1" }] },
    scoreline_grid: { scorelines: [{ home: 0, away: 1, p: 0.1 }, { home: 1, away: 1, p: 0.12 }] },
    prediction_card: { result: "away", scoreline: "1-2", confidence: "low" },
    key_player_duel: { title: "Duel", home_player: { name: "X", number: 4 }, away_player: { name: "Y", number: 9 }, home_stats: [], away_stats: [] },
  };
  for (const [template, data] of Object.entries(DATA)) {
    it(`${template}: no #101820 fill or background`, () => {
      for (const size of SIZES) {
        const html = render(graphicProps(template, data, size));
        expect(html).not.toMatch(/background:\s*#101820/i);
        expect(html).toMatch(/#f2c230/i);
      }
    });
  }
  it("probability_bar: the away segment is the gold secondary and the track is not a team colour", () => {
    const html = render(graphicProps("probability_bar", DATA.probability_bar!));
    expect(html).toMatch(/background:#f2c230/);
    expect(html).toMatch(/background:rgba\(255,255,255,0\.060\);box-shadow:inset 0 0 0 [\d.]+px rgba\(255,255,255,0\.140\)/);
  });
});

describe("stat_compare lower-is-better rows", () => {
  it("helpers: rank fractions, ordinals and flags", () => {
    expect(rankFractions(17, 10)).toEqual([10 / 17, 1]);
    expect(rankFractions(1, 2)).toEqual([1, 0.5]);
    expect(rankFractions(3, null)).toEqual([1, null]);
    expect(rankFractions(0, "x")).toEqual([null, null]);
    expect([1, 2, 3, 4, 11, 12, 13, 17, 21, 22, 101].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "17th", "21st", "22nd", "101st"]);
    expect([0, -1, 2.5, "3", null].map(ordinal)).toEqual([null, null, null, null, null]);
    expect(lowerBetterFlags([true, false], 3)).toEqual([true, false, false]);
    expect(lowerBetterFlags("junk", 2)).toEqual([false, false]);
  });

  const barW = (html: string, color: string): number[] =>
    [...html.matchAll(new RegExp(`width:([\\d.]+)px;height:[\\d.]+px;background:${color}`, "gi"))].map((m) => Number(m[1]));

  it("gives the better league position the longer bar and prints ordinals", () => {
    const p = graphicProps("stat_compare", { labels: ["League position", "Points"], home: [17, 7], away: [10, 12], lower_better: [true, false] });
    const html = render(p);
    const [hPos, hPts] = barW(html, UNITED.fill);
    const [aPos, aPts] = barW(html, VILLA.ring);
    expect(aPos!).toBeGreaterThan(hPos!); // 10th beats 17th
    expect(hPos! / aPos!).toBeCloseTo(10 / 17, 2);
    expect(aPts!).toBeGreaterThan(hPts!); // points stay "more is more"
    const text = html.replace(/<[^>]+>/g, " ");
    expect(text).toContain("17th");
    expect(text).toContain("10th");
    expect(text).not.toMatch(/\b7th\b/); // the points row keeps plain numbers
  });
  it("without the flag a position row is a plain magnitude (old behaviour)", () => {
    const html = render(graphicProps("stat_compare", { labels: ["League position"], home: [17], away: [10] }));
    expect(barW(html, UNITED.fill)[0]!).toBeGreaterThan(barW(html, VILLA.ring)[0]!);
  });
});

describe("scene-title chip", () => {
  it("is never laid out on a graphic scene or over a graphic card", () => {
    const p = readJson<RenderProps>("tests", "fixtures", "graphics", "key_player_duel.json");
    expect(p.scenes[0]!.kind).toBe("graphic");
    for (let f = 0; f < 60; f++) {
      expect(sceneTitleLayout(p, f)).toBeNull();
      expect(hudRects(p, f).length).toBeLessThanOrEqual(1); // a caption at most, never a chip
    }
  });
  it("still shows on a pitch scene", () => {
    const p = fixture();
    const s = p.scenes.find((x) => x.kind === "pitch" && x.title.trim() !== "")!;
    expect(sceneTitleLayout(p, s.from)).not.toBeNull();
  });
  it("is suppressed on a pitch scene while a graphic card is on screen", () => {
    const p = fixture();
    const s = p.scenes.find((x) => x.kind === "pitch" && x.title.trim() !== "")!;
    p.graphics = [{ id: "G", template: "text_card", from: s.from, to: s.from + 30, data: {}, reveals: [] }];
    expect(sceneTitleLayout(p, s.from)).toBeNull();
    expect(sceneTitleLayout(p, s.from + 30)).not.toBeNull();
  });
});
