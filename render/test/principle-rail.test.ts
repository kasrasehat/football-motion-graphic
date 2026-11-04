// The tactic still's key panel: whole titles, nothing truncated, and it fits whatever the tactic_spec schema allows.
import { createRequire } from "node:module";
import React from "react";
import { describe, expect, it } from "vitest";
import { PrincipleRailPanel } from "../src/components/PrincipleRail";
import type { PrincipleRail, RenderProps } from "../src/generated/render_props";
import { railMetrics, wrappedLines } from "../src/lib/rail";
import { fixture, readJson } from "./helpers";

const { renderToStaticMarkup } = createRequire(import.meta.url)("react-dom/server") as {
  renderToStaticMarkup: (el: React.ReactElement) => string;
};

const FILES = ["landscape", "portrait", "square"] as const;
const still = (o: (typeof FILES)[number]) => readJson<RenderProps>("tests", "fixtures", "still", `props.${o}.json`);

/** The most the tactic_spec schema lets through: 6 principles, 40-char names, a 70-char title, all 22 players each. */
function worstCase(rect: PrincipleRail["rect"]): PrincipleRail {
  const players = Array.from({ length: 22 }, (_, i) => ({ team: i < 11 ? ("H" as const) : ("A" as const), number: 78 + (i % 11) }));
  return {
    rect,
    title: "Wolverhampton Wanderers v Borussia Monchengladbach: expected shapes xx",
    ball: { team: "A", number: 88, name: "Maximiliano Fitzgerald-Montgomery" },
    principles: Array.from({ length: 6 }, (_, i) => ({ id: `P${i + 1}`, name: `Wide centre-backs split around the ${i}xxx`, players })),
  };
}

describe("railMetrics", () => {
  it.each(FILES)("%s: the worst case the schema allows fits the panel", (o) => {
    const p = still(o);
    const rail = worstCase(p.principleRail!.rect);
    const m = railMetrics(rail, p.width, p.height);
    expect(m.height).toBeLessThanOrEqual(rail.rect[3] - rail.rect[1]);
    expect(m.nameSize).toBeGreaterThanOrEqual(12);
  });

  it("the real three principles get bigger type than the worst case", () => {
    const p = still("landscape");
    const real = railMetrics(p.principleRail!, p.width, p.height);
    const worst = railMetrics(worstCase(p.principleRail!.rect), p.width, p.height);
    expect(real.nameSize).toBeGreaterThan(worst.nameSize);
    expect(real.height).toBeLessThanOrEqual(p.principleRail!.rect[3] - p.principleRail!.rect[1]);
  });

  it("uses one column in the tall panel, two in the wide one", () => {
    expect(railMetrics(still("landscape").principleRail!, 1920, 1080).columns).toBe(1);
    expect(railMetrics(still("portrait").principleRail!, 1080, 1920).columns).toBe(2);
    expect(railMetrics(still("square").principleRail!, 1080, 1080).columns).toBe(2);
  });
});

describe("wrappedLines", () => {
  it("counts wrapped lines", () => {
    expect(wrappedLines("Short", 500, 20, "title", 0)).toBe(1);
    expect(wrappedLines("one two three four five six seven eight", 60, 20, "title", 0)).toBeGreaterThan(3);
  });

  it("gives a word wider than the line as many lines as it needs", () => {
    expect(wrappedLines("x".repeat(40), 100, 20, "title", 0)).toBeGreaterThanOrEqual(4);
  });
});

describe("PrincipleRailPanel", () => {
  it("draws nothing when the props have no panel (every video)", () => {
    expect(renderToStaticMarkup(React.createElement(PrincipleRailPanel, { props: fixture() }))).toBe("");
  });

  it.each(FILES)("%s: shows every name whole, and every player of every principle", (o) => {
    const p = still(o);
    const html = renderToStaticMarkup(React.createElement(PrincipleRailPanel, { props: p }));
    const rail = p.principleRail!;
    expect(html).not.toMatch(/NaN|undefined|Infinity|\[object Object\]|…|ellipsis/);
    expect(html).toContain(rail.title);
    expect(html).toContain(rail.ball.name!);
    for (const pr of rail.principles) {
      expect(html).toContain(pr.id);
      expect(html).toContain(pr.name);
    }
    const chips = rail.principles.reduce((n, pr) => n + pr.players.length, 0) + 1;
    expect((html.match(/tabular-nums/g) ?? []).length).toBe(chips);
  });

  it("copes with no holder name (show_names off)", () => {
    const p = still("landscape");
    p.principleRail!.ball.name = null;
    const html = renderToStaticMarkup(React.createElement(PrincipleRailPanel, { props: p }));
    expect(html).not.toMatch(/null|undefined/);
  });
});
