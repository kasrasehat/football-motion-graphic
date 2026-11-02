import { describe, expect, it } from "vitest";
import {
  barFractions,
  contentRect,
  ellipsize,
  fitName,
  formatMatchDay,
  formatValue,
  formPoints,
  largestRemainder,
  layoutMode,
  lineupRows,
  nameCandidates,
  normLineup,
  normResults,
  parseFormation,
  parseScore,
  percentText,
  REVEAL_STAGGER,
  revealFrame,
  revealProgress,
  shellLayout,
  splitRow,
  surname,
  teamSide,
  type LineupPlayer,
} from "../src/lib/graphics";
import { estimateTextWidth } from "../src/lib/layout";
import { fixture } from "./helpers";

describe("largestRemainder", () => {
  const sum = (a: number[]) => a.reduce((s, x) => s + x, 0);
  it("rounds the fixture probabilities to 47/25/28 (sums to 100)", () => {
    expect(largestRemainder([0.4735, 0.2448, 0.2817])).toEqual([47, 25, 28]);
  });
  it("splits thirds 34/33/33 (ties go to the earlier index)", () => {
    expect(largestRemainder([1 / 3, 1 / 3, 1 / 3])).toEqual([34, 33, 33]);
  });
  it("keeps exact values exact", () => {
    expect(largestRemainder([0.47, 0.24, 0.29])).toEqual([47, 24, 29]);
    expect(largestRemainder([1, 0, 0])).toEqual([100, 0, 0]);
  });
  it("always sums to the total for many deterministic inputs", () => {
    let seed = 12345;
    const next = () => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed / 2147483648;
    };
    for (let i = 0; i < 2000; i++) {
      const v = [next(), next(), next()];
      const r = largestRemainder(v);
      expect(sum(r)).toBe(100);
      r.forEach((x, j) => expect(Math.abs(x - (v[j]! / sum(v)) * 100)).toBeLessThan(1));
    }
    for (let n = 1; n <= 8; n++) expect(sum(largestRemainder(Array.from({ length: n }, (_, k) => k + 0.37)))).toBe(100);
  });
  it("treats junk as 0 and returns zeros when nothing is positive", () => {
    expect(largestRemainder([null, 0.5, "x", -2])).toEqual([0, 100, 0, 0]);
    expect(largestRemainder([0, 0, 0])).toEqual([0, 0, 0]);
    expect(largestRemainder([])).toEqual([]);
  });
});

describe("reveal gating", () => {
  const g = (frames: number[], from = 20) => ({ from, reveals: frames.map((frame, i) => ({ id: `R${i + 1}`, frame })) });
  it("item i appears at reveal i", () => {
    const s = g([30, 45, 60]);
    expect([0, 1, 2].map((i) => revealFrame(s, i))).toEqual([30, 45, 60]);
  });
  it("items beyond the last reveal appear with the last one", () => {
    const s = g([30, 45]);
    expect([2, 3, 9].map((i) => revealFrame(s, i))).toEqual([45, 45, 45]);
  });
  it("with no reveals everything enters from `from`, staggered", () => {
    const s = g([], 12);
    expect([0, 1, 2].map((i) => revealFrame(s, i))).toEqual([12, 12 + REVEAL_STAGGER, 12 + 2 * REVEAL_STAGGER]);
    expect(revealFrame(s, 3, 2)).toBe(18);
  });
  it("never reveals before the graphic starts", () => {
    expect(revealFrame(g([5, 40]), 0)).toBe(20);
  });
  it("progress is 0 before the reveal, > 0 on it, 1 after `frames`", () => {
    expect(revealProgress(29, 30, 10)).toBe(0);
    expect(revealProgress(30, 30, 10)).toBeGreaterThan(0);
    expect(revealProgress(34, 30, 10)).toBeLessThan(1);
    expect(revealProgress(39, 30, 10)).toBe(1);
    expect(revealProgress(500, 30, 10)).toBe(1);
  });
});

describe("value helpers", () => {
  it("formats stat values with units", () => {
    expect(formatValue(2.3)).toBe("2.3");
    expect(formatValue(58, "%")).toBe("58%");
    expect(formatValue(55.25, "%")).toBe("55.3%");
    expect(formatValue(0.456)).toBe("0.46");
    expect(formatValue(2.1, "xG")).toBe("2.1 xG");
    expect(formatValue(123.4)).toBe("123");
    expect(formatValue("1st", "%")).toBe("1st");
    expect(formatValue(null)).toBe("–");
    expect(formatValue(Number.NaN)).toBe("–");
  });
  it("bars are proportional to the max of the pair; strings/null get none", () => {
    expect(barFractions(2, 4)).toEqual([0.5, 1]);
    expect(barFractions(3, null)).toEqual([1, null]);
    expect(barFractions("1st", "2nd")).toEqual([null, null]);
    expect(barFractions(0, 0)).toEqual([0, 0]);
    expect(barFractions(-1, 2)).toEqual([0, 1]);
  });
  it("percent text", () => {
    expect(percentText(0.118)).toBe("11.8%");
    expect(percentText(undefined)).toBe("–");
  });
});

describe("results, scores, dates, teams", () => {
  const theme = fixture().theme;
  theme.teams.H = { ...theme.teams.H, name: "Real Madrid", short: "RMA" };
  theme.teams.A = { ...theme.teams.A, name: "Arsenal", short: "ARS" };
  it("normalises form lists and counts points", () => {
    expect(normResults(["W", "d", "L", "x", 3, "Win"])).toEqual(["W", "D", "L", "W"]);
    expect(normResults("WWDL")).toEqual(["W", "W", "D", "L"]);
    expect(normResults(null)).toEqual([]);
    expect(formPoints(["W", "W", "D", "W", "L"])).toBe(10);
  });
  it("parses scores", () => {
    expect(parseScore("2-1")).toEqual([2, 1]);
    expect(parseScore("0 – 0")).toEqual([0, 0]);
    expect(parseScore("3:2")).toEqual([3, 2]);
    expect(parseScore("abc")).toBeNull();
    expect(parseScore(21)).toBeNull();
  });
  it("formats ISO days without a clock", () => {
    expect(formatMatchDay("2025-04-16")).toEqual({ day: "16 APR", year: "2025", full: "16 APR 2025" });
    expect(formatMatchDay("last week").full).toBe("last week");
    expect(formatMatchDay(undefined).full).toBe("");
  });
  it("matches free-text team names to the theme", () => {
    expect(teamSide("Real Madrid", theme)).toBe("H");
    expect(teamSide("ARSENAL", theme)).toBe("A");
    expect(teamSide("Arsenal FC", theme)).toBe("A");
    expect(teamSide("Réal  Madrid", theme)).toBe("H");
    expect(teamSide("Bayern", theme)).toBeNull();
    expect(teamSide(null, theme)).toBeNull();
  });
});

describe("line-ups", () => {
  const P = (position: LineupPlayer["position"], n: number): LineupPlayer => ({ name: `P${n}`, number: n, position });
  const xi = [P("G", 1), P("D", 2), P("D", 3), P("D", 4), P("D", 5), P("M", 6), P("M", 7), P("M", 8), P("F", 9), P("F", 10), P("F", 11)];
  const sizes = (rows: LineupPlayer[][]) => rows.map((r) => r.length);
  it("parses formations", () => {
    expect(parseFormation("4-2-3-1")).toEqual([4, 2, 3, 1]);
    expect(parseFormation(" 3–5–2 ")).toEqual([3, 5, 2]);
    expect(parseFormation("442")).toBeNull();
    expect(parseFormation("4-0-6")).toBeNull();
    expect(parseFormation(null)).toBeNull();
  });
  it("uses the formation when it accounts for every outfield player", () => {
    expect(sizes(lineupRows(xi, "4-3-3"))).toEqual([1, 4, 3, 3]);
    const fx = xi.map((p, i) => (i >= 6 && i <= 8 ? { ...p, position: "M" as const } : p));
    expect(sizes(lineupRows(fx, "4-2-3-1"))).toEqual([1, 4, 2, 3, 1]);
  });
  it("falls back to position counts (and splits long rows)", () => {
    expect(sizes(lineupRows(xi, "4-4-3"))).toEqual([1, 4, 3, 3]); // 11 outfield in the formation, 10 on the sheet
    expect(sizes(lineupRows(xi))).toEqual([1, 4, 3, 3]);
    const mids = [P("G", 1), P("D", 2), P("D", 3), P("D", 4), P("M", 5), P("M", 6), P("M", 7), P("M", 8), P("M", 9), P("M", 10), P("F", 11)];
    expect(sizes(lineupRows(mids))).toEqual([1, 3, 3, 3, 1]);
    expect(sizes(lineupRows(xi.slice(1)))).toEqual([4, 3, 3]); // no keeper
    expect(lineupRows([])).toEqual([]);
  });
  it("orders by position whatever the input order", () => {
    const rows = lineupRows([...xi].reverse(), "4-3-3");
    expect(rows[0]![0]!.position).toBe("G");
    expect(rows[3]!.every((p) => p.position === "F")).toBe(true);
  });
  it("splitRow balances", () => {
    expect(splitRow([1, 2, 3, 4, 5, 6]).map((r) => r.length)).toEqual([3, 3]);
    expect(splitRow([1, 2, 3, 4, 5, 6, 7]).map((r) => r.length)).toEqual([4, 3]);
    expect(splitRow([1, 2]).map((r) => r.length)).toEqual([2]);
  });
  it("reads lineups leniently", () => {
    const l = normLineup([{ name: "A", number: 7.2, position: "Goalkeeper" }, null, "x", { name: 3 }, { name: "B", position: "ATT" }]);
    expect(l).toEqual([
      { name: "A", number: 7, position: "G" },
      { name: "", number: null, position: "M" },
      { name: "B", number: null, position: "F" },
    ]);
    expect(normLineup(Array.from({ length: 15 }, () => ({ name: "x" }))).length).toBe(11);
  });
});

describe("names and text", () => {
  it("shirt surnames keep particles and suffixes", () => {
    expect(surname("Frenkie de Jong")).toBe("de Jong");
    expect(surname("Vinícius Júnior")).toBe("Vinícius Júnior");
    expect(surname("Trent Alexander-Arnold")).toBe("Alexander-Arnold");
    expect(surname("Rodrygo")).toBe("Rodrygo");
    expect(nameCandidates("Vinícius Júnior")).toEqual(["Vinícius Júnior", "Vinícius"]);
  });
  it("fitName shortens only when needed", () => {
    expect(fitName("Jude Bellingham", 1000, 22)).toBe("Jude Bellingham");
    expect(fitName("Jude Bellingham", 120, 22)).toBe("Bellingham");
    expect(fitName("Vinícius Júnior", 110, 22)).toBe("Vinícius");
    expect(fitName("", 100, 22)).toBe("");
  });
  it("ellipsize fits the estimate", () => {
    const t = ellipsize("A very long player name indeed", 120, 24, "body");
    expect(t.endsWith("…")).toBe(true);
    expect(estimateTextWidth(t, 24, "body")).toBeLessThanOrEqual(120);
    expect(ellipsize("Short", 500, 24)).toBe("Short");
  });
});

describe("orientation-aware layout", () => {
  const sizes: [number, number][] = [
    [1920, 1080],
    [1080, 1920],
    [1080, 1080],
    [960, 540],
  ];
  it("classifies orientation", () => {
    expect(layoutMode(1920, 1080)).toBe("landscape");
    expect(layoutMode(1080, 1920)).toBe("portrait");
    expect(layoutMode(1080, 1080)).toBe("square");
  });
  it("keeps the lower 22% clear and stays inside the safe area", () => {
    for (const [w, h] of sizes) {
      const c = contentRect(w, h);
      expect(c.y1).toBeLessThanOrEqual(h * 0.78 + 1e-9);
      for (const bodyH of [undefined, 0, 200, 1e9]) {
        const L = shellLayout(w, h, { bodyH });
        expect(L.panel.x0).toBeGreaterThanOrEqual(c.x0 - 1e-9);
        expect(L.panel.x1).toBeLessThanOrEqual(c.x1 + 1e-9);
        expect(L.panel.y0).toBeGreaterThanOrEqual(c.y0 - 1e-9);
        expect(L.panel.y1).toBeLessThanOrEqual(c.y1 + 1e-9);
        expect(L.bodyH).toBeLessThanOrEqual(L.maxBodyH + 1e-9);
        expect(L.body.y1).toBeLessThanOrEqual(L.panel.y1);
      }
    }
  });
});
