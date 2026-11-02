import { describe, expect, it } from "vitest";
import type { RenderProps } from "../src/generated/render_props";
import { assertRenderProps, checkConsistency, RenderPropsError, validateSchema } from "../src/lib/validate";
import { calculateTacticMetadata } from "../src/TacticVideo.meta";
import { fixture } from "./helpers";

type Mut = (p: Record<string, any>) => void;

const MUTATIONS: [string, Mut, RegExp][] = [
  ["wrong fps", (p) => (p.fps = 25), /\/fps must be equal to constant: 30/],
  ["missing tracks", (p) => delete p.tracks, /must have required property 'tracks'/],
  ["bad hex colour", (p) => (p.theme.accent = "#ffd54"), /\/theme\/accent must match pattern/],
  ["bad team hex colour", (p) => (p.theme.teams.H.fill = "red"), /\/theme\/teams\/H\/fill must match pattern/],
  ["unknown overlay kind", (p) => (p.overlays[0].kind = "arrow"), /\/overlays\/0\/kind must be equal to one of the allowed values/],
  ["extra top-level key", (p) => (p.extra = 1), /must NOT have additional properties: 'extra'/],
  ["unsupported size", (p) => (p.width = 1280), /\/width must be equal to one of the allowed values/],
  ["caption line too long", (p) => (p.captions[0].lines = ["x".repeat(43)]), /\/captions\/0\/lines\/0 must NOT have more than 42 characters/],
  ["bad entity id", (p) => (p.entities[0].id = "H12"), /\/entities\/0\/id must match pattern/],
  ["no scenes", (p) => (p.scenes = []), /\/scenes must NOT have fewer than 1 items/],
  ["bad anim", (p) => (p.overlays[0].inAnim.anim = "wipe"), /\/overlays\/0\/inAnim\/anim must be equal to one of the allowed values/],
  ["geom both forms", (p) => (p.overlays[0].geom = { static: [], perFrame: [] }), /\/overlays\/0\/geom/],
];

describe("ajv schema validation", () => {
  it("accepts the fixture", () => {
    const r = validateSchema(fixture());
    expect(r.errors).toEqual([]);
    expect(r.ok).toBe(true);
    expect(checkConsistency(fixture())).toEqual([]);
  });

  for (const [name, mut, msg] of MUTATIONS) {
    it(`rejects: ${name}`, () => {
      const p = fixture() as unknown as Record<string, any>;
      mut(p);
      const r = validateSchema(p);
      expect(r.ok).toBe(false);
      expect(r.errors.join("\n")).toMatch(msg);
      expect(() => assertRenderProps(p)).toThrow(RenderPropsError);
    });
  }

  it("throws a readable error listing every problem", () => {
    const p = fixture() as unknown as Record<string, any>;
    p.fps = 24;
    p.theme.warn = "nope";
    try {
      assertRenderProps(p);
      expect.unreachable();
    } catch (e) {
      const m = (e as Error).message;
      expect(m).toMatch(/^Invalid render_props \(2 problems\):/);
      expect(m).toContain("/fps");
      expect(m).toContain("/theme/warn");
    }
  });
});

describe("consistency checks (not expressible in the schema)", () => {
  it("flags per-frame arrays whose length does not match durationInFrames", () => {
    const p = fixture();
    p.tracks.players["H4"] = p.tracks.players["H4"]!.slice(0, 10);
    p.camera = p.camera.slice(0, 30);
    const errs = checkConsistency(p);
    expect(errs.some((e) => e.includes("/tracks/players/H4"))).toBe(true);
    expect(errs.some((e) => e.includes("/camera"))).toBe(true);
    expect(() => assertRenderProps(p)).toThrow(/tracks\/players\/H4/);
  });
  it("flags orientation / size mismatch and entities without tracks", () => {
    const p = fixture();
    p.orientation = "portrait";
    delete p.tracks.players["A9"];
    const errs = checkConsistency(p);
    expect(errs.some((e) => e.includes("portrait"))).toBe(true);
    expect(errs.some((e) => e.includes("A9"))).toBe(true);
  });
});

describe("calculateMetadata", () => {
  it("derives duration / fps / size from props", async () => {
    const p = fixture() as RenderProps & Record<string, unknown>;
    const m = await calculateTacticMetadata({
      props: p,
      defaultProps: p,
      abortSignal: new AbortController().signal,
      compositionId: "TacticVideo",
      isRendering: true,
    });
    expect(m).toMatchObject({ durationInFrames: 90, fps: 30, width: 1920, height: 1080 });
    const por = { ...p, orientation: "portrait" as const, width: 1080 as const, height: 1920 as const };
    const m2 = await calculateTacticMetadata({
      props: por,
      defaultProps: p,
      abortSignal: new AbortController().signal,
      compositionId: "TacticVideo",
      isRendering: true,
    });
    expect(m2).toMatchObject({ width: 1080, height: 1920 });
  });
  it("throws on invalid props", () => {
    const p = fixture() as unknown as RenderProps & Record<string, unknown>;
    (p as Record<string, unknown>).fps = 60;
    expect(() =>
      calculateTacticMetadata({
        props: p,
        defaultProps: p,
        abortSignal: new AbortController().signal,
        compositionId: "TacticVideo",
        isRendering: true,
      }),
    ).toThrow(/Invalid render_props/);
  });
});
