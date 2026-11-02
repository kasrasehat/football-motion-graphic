import { describe, expect, it } from "vitest";
import type { Caption } from "../src/generated/render_props";
import {
  activeCaption,
  activeWordIndex,
  CAPTION_BASE_PX_1080,
  CAPTION_PAD_X_1080,
  captionFontSize,
  captionLines,
  wordState,
} from "../src/lib/captions";
import { estimateTextWidth, safeArea } from "../src/lib/layout";
import { fixture } from "./helpers";

const cap = (): Caption => fixture().captions[0]!;

describe("caption selection", () => {
  it("is visible on [from, to) only", () => {
    const caps = fixture().captions;
    expect(activeCaption(caps, 19)).toBeNull();
    expect(activeCaption(caps, 20)).not.toBeNull();
    expect(activeCaption(caps, 63)).not.toBeNull();
    expect(activeCaption(caps, 64)).toBeNull();
  });
  it("earliest-starting caption wins on overlap", () => {
    const a = { ...cap(), from: 0, to: 50 };
    const b = { ...cap(), from: 40, to: 80, lines: ["second"] as [string] };
    expect(activeCaption([b, a], 45)).toBe(a);
    expect(activeCaption([b, a], 55)).toBe(b);
  });
});

describe("active word", () => {
  it("follows the word timings (half-open) and is -1 between words / after the last word", () => {
    const c = cap(); // The 20-26, right-back 26-38, steps 38-46, inside. 46-60
    expect(activeWordIndex(c, 20)).toBe(0);
    expect(activeWordIndex(c, 25)).toBe(0);
    expect(activeWordIndex(c, 26)).toBe(1);
    expect(activeWordIndex(c, 45)).toBe(2);
    expect(activeWordIndex(c, 46)).toBe(3);
    expect(activeWordIndex(c, 59)).toBe(3);
    expect(activeWordIndex(c, 60)).toBe(-1);
    const gap: Caption = { ...c, words: [{ t: "a", from: 20, to: 25, line: 0 }, { t: "b", from: 30, to: 35, line: 0 }] };
    expect(activeWordIndex(gap, 27)).toBe(-1);
  });
  it("marks past / active / future", () => {
    const c = cap();
    const states = captionLines(c, 40)[0]!.map((w) => w.state);
    expect(states).toEqual(["past", "past", "active", "future"]);
    expect(wordState(c.words[0]!, 10)).toBe("future");
    expect(wordState(c.words[0]!, 26)).toBe("past");
  });
  it("splits words into at most 2 lines by word.line", () => {
    const c: Caption = {
      from: 0,
      to: 30,
      lines: ["one two", "three"],
      words: [
        { t: "one", from: 0, to: 5, line: 0 },
        { t: "two", from: 5, to: 10, line: 0 },
        { t: "three", from: 10, to: 20, line: 1 },
      ],
      place: "top",
    };
    const ls = captionLines(c, 12);
    expect(ls.map((l) => l.map((w) => w.text))).toEqual([["one", "two"], ["three"]]);
    expect(ls[1]![0]!.state).toBe("active");
  });
  it("falls back to plain lines without word timing", () => {
    const c: Caption = { from: 0, to: 30, lines: ["no timing here"], words: [], place: "bottom" };
    expect(captionLines(c, 5)[0]!.map((w) => w.text)).toEqual(["no", "timing", "here"]);
  });
});

describe("caption size", () => {
  it("is 44 px at 1080p for normal lines", () => {
    expect(captionFontSize(["The right-back steps inside."], 1920, 1080)).toBeCloseTo(CAPTION_BASE_PX_1080, 9);
    expect(captionFontSize(["The right-back steps inside."], 960, 540)).toBeCloseTo(CAPTION_BASE_PX_1080 / 2, 9);
  });
  it("shrinks only as needed so 42-char lines fit the 90% safe area, even in portrait", () => {
    const worst = ["WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW"];
    for (const [w, h] of [
      [1080, 1920],
      [1080, 1080],
      [1920, 1080],
    ] as const) {
      const fs = captionFontSize(worst, w, h);
      const safe = safeArea(w, h);
      const unit = Math.min(w, h) / 1080;
      expect(fs).toBeLessThanOrEqual(CAPTION_BASE_PX_1080 * unit + 1e-9);
      expect(estimateTextWidth(worst[0]!, fs, "body")).toBeLessThanOrEqual(safe.x1 - safe.x0 - 2 * CAPTION_PAD_X_1080 * unit + 1e-6);
    }
  });
});
