// Generated team flags and kit palettes: the flag is drawn from the kit colours alone (no image, nothing fetched), a
// dark kit keeps a visible edge, the flag waves only as a function of the frame, every comparison card and the
// opening cards carry both flags, a supplied crest still takes a flag's place, and the kit washes on the backdrops
// stay faint enough that text keeps WCAG contrast.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { EndCardView, flagEntry, TitleCardView } from "../src/components/Cards";
import { GRAPHIC_TEMPLATES, isOpeningGraphic } from "../src/components/graphics/registry";
import { TeamFlag } from "../src/components/TeamFlag";
import type { Graphic, RenderProps, Theme } from "../src/generated/render_props";
import { contrastRatio, mix } from "../src/lib/colors";
import {
  backdropLift,
  FLAG_NOTCH,
  flagColors,
  flagShape,
  KIT_HEADER_WASH,
  KIT_WASH_INK_CONTRAST,
  KIT_WASH_MAX,
  kitRule,
  kitTint,
  kitWashAlpha,
} from "../src/lib/flags";
import { cardSurface, CARD_FILL_MIN_CONTRAST, teamLabel } from "../src/lib/graphics";
import { fixture, readJson, RENDER_DIR, REPO_DIR } from "./helpers";

vi.mock("remotion", async (original) => ({
  ...(await original<typeof import("remotion")>()),
  Img: (p: React.ImgHTMLAttributes<HTMLImageElement>) => React.createElement("img", p),
}));

const { renderToStaticMarkup } = createRequire(import.meta.url)("react-dom/server") as {
  renderToStaticMarkup: (el: React.ReactElement) => string;
};

const VILLA = { fill: "#101820", ring: "#f2c230", text: "#ffffff", short: "AVL", name: "Aston Villa" };
const UNITED = { fill: "#da291c", ring: "#ffffff", text: "#ffffff", short: "MUN", name: "Manchester United" };
const PNG = "data:image/png;base64,iVBORw0KGgo=";

const COMPARISON = [
  "stat_compare",
  "form_guide",
  "team_news",
  "pattern_compare",
  "probability_bar",
  "prediction_card",
  "key_player_duel",
  "lineup_board",
  "h2h_strip",
] as const;

const SIZES: Pick<RenderProps, "width" | "height" | "orientation">[] = [
  { width: 1920, height: 1080, orientation: "landscape" },
  { width: 1080, height: 1920, orientation: "portrait" },
  { width: 1080, height: 1080, orientation: "square" },
];

/** All kit palettes of config/themes.yaml (fill, ring, text), read without a YAML parser. */
function palettes(): [string, string, string][] {
  const y = readFileSync(join(REPO_DIR, "config", "themes.yaml"), "utf8");
  return [...y.matchAll(/^\s+\w+: \["(#[0-9a-f]{6})", "(#[0-9a-f]{6})", "(#[0-9a-f]{6})"\]/gim)].map((m) => [m[1]!, m[2]!, m[3]!]);
}

/** Both UI themes of config/themes.yaml. */
function uiThemes(): Theme[] {
  const y = readFileSync(join(REPO_DIR, "config", "themes.yaml"), "utf8");
  const base = fixture().theme;
  const out: Theme[] = [];
  for (const m of y.matchAll(/pitch: \{grass: "(#\w+)", stripe: "(#\w+)", line: "(#\w+)"\}\s+ui: \{accent: "(#\w+)", warn: "(#\w+)", ink: "(#\w+)", panel: "(#\w+)"\}/g)) {
    out.push({ ...base, pitch: { grass: m[1]!, stripe: m[2]!, line: m[3]! }, accent: m[4]!, warn: m[5]!, ink: m[6]!, panel: m[7]! });
  }
  return out;
}

const kit = ([fill, ring, text]: [string, string, string], short = "T", name = "Team") => ({ fill, ring, text, short, name });
const theme = (H = UNITED, A = VILLA): Theme => ({ ...fixture().theme, teams: { H: { ...H }, A: { ...A } } });

function graphicProps(template: string, size: Partial<RenderProps> = {}, teams: Theme["teams"] = theme().teams): RenderProps {
  const p = readJson<RenderProps>("tests", "fixtures", "graphics", `${template}.json`);
  p.theme.teams = { H: { ...teams.H }, A: { ...teams.A } };
  return { ...p, ...size };
}

function render(p: RenderProps, frame = 75): string {
  const g: Graphic = p.graphics[0]!;
  return renderToStaticMarkup(React.createElement(GRAPHIC_TEMPLATES[g.template], { g, props: p, frame }));
}

const flags = (html: string, side: "H" | "A") => html.split(`data-flag="${side}"`).length - 1;

describe("flag colours come from the kit", () => {
  it("field = shirt, band = trim, pinstripe = number colour when it adds a third colour", () => {
    const h = flagColors(theme(), "H");
    expect([h.field, h.band, h.stripe]).toEqual([UNITED.fill, UNITED.ring, null]); // white number = white trim: no stripe
    const a = flagColors(theme(), "A");
    expect([a.field, a.band, a.stripe]).toEqual([VILLA.fill, VILLA.ring, VILLA.text]);
  });
  it("a dark kit keeps an edge that stands off the card (Villa navy gets its gold trim)", () => {
    const bg = cardSurface(theme());
    expect(contrastRatio(VILLA.fill, bg)).toBeLessThan(CARD_FILL_MIN_CONTRAST);
    expect(contrastRatio(flagColors(theme(), "A").edge, bg)).toBeGreaterThanOrEqual(CARD_FILL_MIN_CONTRAST);
  });
  it("an all-black kit gets a light edge and a band that differs from the field", () => {
    const black = { fill: "#101820", ring: "#101820", text: "#101820", short: "BLK", name: "Black" };
    const c = flagColors(theme(UNITED, black), "A");
    expect(c.band).not.toBe(c.field);
    expect(contrastRatio(c.band, c.field)).toBeGreaterThan(1.45);
    expect(c.edge).toMatch(/rgba\(255,255,255/);
  });
  it("every palette of the intake template gives a two-colour flag", () => {
    for (const p of palettes()) {
      const c = flagColors(theme(kit(p)), "H");
      expect(contrastRatio(c.band, c.field), p.join()).toBeGreaterThanOrEqual(1.45);
    }
  });
});

describe("flag geometry", () => {
  it("is a swallowtail: the notch point sits FLAG_NOTCH in from the fly at mid height", () => {
    const s = flagShape(150, 100);
    expect(s.outline).toContain(`${150 * (1 - FLAG_NOTCH)},50`);
    expect(s.outline.startsWith("M0,0")).toBe(true);
  });
  it("is flat without amplitude and waves with it, a pure function of (phase, amplitude)", () => {
    const flat = flagShape(150, 100, 3, 0);
    const ys = [...flat.outline.matchAll(/[\d.]+,(-?[\d.]+)/g)].map((m) => Number(m[1]));
    expect(new Set(ys)).toEqual(new Set([0, 50, 100]));
    const a = flagShape(150, 100, 1.2, 0.05);
    expect(a).toEqual(flagShape(150, 100, 1.2, 0.05));
    expect(a.outline).not.toBe(flagShape(150, 100, 1.4, 0.05).outline);
    expect(a.outline).not.toContain("NaN");
  });
  it("the hoist does not move while the cloth waves", () => {
    for (const ph of [0, 1, 2, 3]) expect(flagShape(150, 100, ph, 0.06).outline.startsWith("M0,0 ")).toBe(true);
  });
  it("draws as SVG paths only: no image, no external reference", () => {
    const html = renderToStaticMarkup(React.createElement(TeamFlag, { theme: theme(), side: "A", h: 60, uid: "t", phase: 1, amp: 0.05 }));
    expect(html).not.toMatch(/<img|<image|href=|https?:/);
    expect(html).toContain(VILLA.fill);
    expect(html).toContain(VILLA.ring);
    expect(html).toContain('data-flag="A"');
    expect(html).toContain("scale(-1 1)"); // the away flag faces the home flag
  });
});

describe("flags on the cards", () => {
  it("every two-team comparison card shows both flags in every orientation", () => {
    for (const t of COMPARISON)
      for (const size of SIZES) {
        const html = render(graphicProps(t, size));
        expect(flags(html, "H"), `${t} ${size.orientation}`).toBeGreaterThanOrEqual(1);
        expect(flags(html, "A"), `${t} ${size.orientation}`).toBeGreaterThanOrEqual(1);
      }
  });
  it("the comparison cards also put a flag beside the team names where they are labelled", () => {
    for (const t of ["stat_compare", "form_guide", "team_news", "pattern_compare", "probability_bar", "lineup_board", "key_player_duel"]) {
      const html = render(graphicProps(t));
      expect(flags(html, "H"), t).toBeGreaterThanOrEqual(2);
      expect(flags(html, "A"), t).toBeGreaterThanOrEqual(2);
    }
  });
  it("the title card and the title_card graphic show both flags, flying in from the frame number", () => {
    const p = { ...graphicProps("stat_compare"), titleCard: { from: 0, to: 60, title: "Manchester United v Aston Villa", subtitle: "Preview" } };
    const at = (f: number) => renderToStaticMarkup(React.createElement(TitleCardView, { props: p, frame: f }));
    expect(flags(at(30), "H")).toBe(1);
    expect(flags(at(30), "A")).toBe(1);
    expect(at(30)).toBe(at(30));
    expect(at(3)).not.toBe(at(4)); // animated by the frame, not by CSS
    expect(flagEntry(0, 0, "H")).toBe(0);
    expect(flagEntry(30, 0, "H")).toBe(1);
    expect(flagEntry(5, 0, "A")).toBeLessThan(flagEntry(5, 0, "H"));
    const g = graphicProps("stat_compare");
    g.graphics[0] = { ...g.graphics[0]!, template: "title_card", data: { headline: "A v B", sub: "x" }, reveals: [] };
    expect(flags(render(g), "H")).toBe(1);
    expect(flags(render(g), "A")).toBe(1);
  });
  it("a supplied crest still takes the flag's place on the title card and in the lock-up", () => {
    const t = theme();
    const teams = { H: { ...t.teams.H, crest: PNG }, A: { ...t.teams.A } };
    const g = graphicProps("stat_compare", {}, teams);
    const html = render(g);
    expect(html).toContain(`src="${PNG}"`);
    const tc = { ...g, titleCard: { from: 0, to: 60, title: "A v B", subtitle: "" } };
    const title = renderToStaticMarkup(React.createElement(TitleCardView, { props: tc, frame: 30 }));
    expect(title).toContain(`src="${PNG}"`);
    expect(flags(title, "H")).toBe(0);
    expect(flags(title, "A")).toBe(1);
  });
  it("the opening text card carries the flags; later text cards do not", () => {
    const p = graphicProps("stat_compare");
    const first: Graphic = { ...p.graphics[0]!, id: "S01", template: "text_card", from: 0, to: 45, data: { title: "History v form", bullets: [] }, reveals: [] };
    const later: Graphic = { ...first, id: "S02", from: 45, to: 90 };
    const q = { ...p, graphics: [first, later] };
    expect(isOpeningGraphic(q, first)).toBe(true);
    expect(isOpeningGraphic(q, later)).toBe(false);
    const html = (g: Graphic, f: number) => renderToStaticMarkup(React.createElement(GRAPHIC_TEMPLATES.text_card, { g, props: q, frame: f }));
    expect(flags(html(first, 30), "H")).toBe(1);
    expect(flags(html(later, 80), "H")).toBe(0);
  });
  it("the end card shows both flags", () => {
    const p = { ...graphicProps("stat_compare"), endCard: { from: 0, to: 60, text: "Thanks" } };
    const html = renderToStaticMarkup(React.createElement(EndCardView, { props: p, frame: 30 }));
    expect(flags(html, "H")).toBe(1);
    expect(flags(html, "A")).toBe(1);
  });
  it("a long team name beside a flag falls back to the short code instead of being cut", () => {
    const t = theme();
    expect(teamLabel(t, "H", 1000, 40)).toBe("Manchester United");
    expect(teamLabel(t, "H", 120, 40)).toBe("MUN");
  });
});

describe("kit palettes keep text legible", () => {
  it("the backdrop wash keeps the ink >= 7:1 (subtitles at 86% ink stay >= 4.5:1) for every palette and theme", () => {
    for (const ui of uiThemes())
      for (const p of [...palettes(), [UNITED.fill, UNITED.ring, UNITED.text] as [string, string, string], [VILLA.fill, VILLA.ring, VILLA.text] as [string, string, string]]) {
        const t: Theme = { ...ui, teams: { H: kit(p), A: kit(p) } };
        const a = kitWashAlpha(t, "H");
        expect(a).toBeLessThanOrEqual(KIT_WASH_MAX);
        const worst = mix(backdropLift(t), kitTint(t, "H"), a);
        expect(contrastRatio(t.ink, worst), p.join()).toBeGreaterThanOrEqual(KIT_WASH_INK_CONTRAST);
        expect(contrastRatio(mix(worst, t.ink, 0.86), worst), p.join()).toBeGreaterThanOrEqual(4.5);
      }
  });
  it("both kits of the reference fixture show (a dark kit washes in its trim colour)", () => {
    const t = theme();
    expect(kitWashAlpha(t, "H")).toBeGreaterThan(0.1);
    expect(kitWashAlpha(t, "A")).toBeGreaterThan(0.1);
    expect(kitTint(t, "A")).toBe(VILLA.ring);
  });
  it("the header wash on data cards keeps body text >= 4.5:1 for every palette", () => {
    for (const p of palettes()) {
      const t = theme(kit(p), kit(p));
      const surface = mix(cardSurface(t), kitTint(t, "H"), KIT_HEADER_WASH);
      expect(contrastRatio(t.ink, surface), p.join()).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("kit rules use both teams' colours and drop the accent when it would merge with a kit", () => {
    const rule = kitRule(theme());
    expect(rule.map(([c]) => c)).toEqual([UNITED.fill, VILLA.ring]); // gold accent next to Villa gold: dropped
    const sky = kit(["#6cabdd", "#ffffff", "#0b2545"]);
    expect(kitRule(theme(UNITED, sky)).map(([c]) => c)).toEqual([UNITED.fill, fixture().theme.accent, sky.fill]);
    for (const r of [rule, kitRule(theme(UNITED, sky))]) expect(r.reduce((s, [, w]) => s + w, 0)).toBeCloseTo(1);
  });
});

describe("determinism of the new files", () => {
  it("uses no clock, randomness or CSS animation", () => {
    for (const f of ["src/lib/flags.ts", "src/components/TeamFlag.tsx", "src/components/Cards.tsx"]) {
      const src = readFileSync(join(RENDER_DIR, f), "utf8");
      expect(src, f).not.toMatch(/Math\.random|Date\b|performance\.now|setTimeout|setInterval|requestAnimationFrame|@keyframes|animation:|transition:/);
    }
  });
});
