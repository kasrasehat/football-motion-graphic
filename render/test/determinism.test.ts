import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { RENDER_DIR } from "./helpers";

// Every frame must be a pure function of (frame, props): no randomness, wall clock, timers or CSS-driven motion.
const FORBIDDEN: [string, RegExp][] = [
  ["Math.random", /Math\s*\.\s*random/],
  ["Date / new Date", /\bDate\b/],
  ["performance.now", /performance\s*\.\s*now/],
  ["timers", /\b(setTimeout|setInterval|setImmediate|queueMicrotask)\s*\(/],
  ["requestAnimationFrame", /\b(requestAnimationFrame|requestIdleCallback)\b/],
  ["CSS @keyframes", /@keyframes/],
  ["CSS animation", /\banimation(Name|Duration|Delay|TimingFunction|IterationCount|PlayState|FillMode|Direction)?\s*:/],
  ["CSS animation (kebab)", /\banimation(-[a-z]+)?\s*:/],
  ["CSS transition", /\btransition(Property|Duration|Delay|TimingFunction)?\s*:/],
  ["CSS transition (kebab)", /\btransition(-[a-z]+)?\s*:/],
  ["SVG SMIL animation", /<\s*(animate|animateTransform|animateMotion|set)\b/],
];

function files(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...files(p));
    else if (/\.(tsx?|css|json)$/.test(name)) out.push(p);
  }
  return out;
}

describe("determinism scan of render/src", () => {
  const src = join(RENDER_DIR, "src");
  const all = files(src);
  it("finds the sources", () => {
    expect(all.length).toBeGreaterThan(10);
  });
  for (const [what, re] of FORBIDDEN) {
    it(`no ${what}`, () => {
      const hits: string[] = [];
      for (const f of all) {
        readFileSync(f, "utf8")
          .split("\n")
          .forEach((line, i) => {
            if (re.test(line)) hits.push(`${relative(src, f)}:${i + 1}: ${line.trim()}`);
          });
      }
      expect(hits).toEqual([]);
    });
  }
  it("the scanner itself catches violations", () => {
    const bad = ["const x = Math.random();", "const t = Date.now();", "setTimeout(f, 1)", "style={{ transition: 'all 1s' }}", "requestAnimationFrame(cb)"];
    for (const line of bad) expect(FORBIDDEN.some(([, re]) => re.test(line))).toBe(true);
  });
});
