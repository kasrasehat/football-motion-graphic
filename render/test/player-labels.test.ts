// Name labels: a one-frame still solves them clear of everything; a video keeps the fixed below-the-token slot.
// The checks use their own geometry rather than the solver's, so they cannot agree with it by construction.
import { describe, expect, it } from "vitest";
import type { RenderProps } from "../src/generated/render_props";
import { estimateTextWidth, type Rect } from "../src/lib/layout";
import { overlayPoints, ringOuterRadiusPx } from "../src/lib/overlays";
import { placePlayerLabels, screenTokens } from "../src/lib/playerLabels";
import { ballRadiusPx, pxPerMetre, tokenRadiusPx, worldToScreen } from "../src/lib/projection";
import { ballAt, cameraAt } from "../src/lib/tracks";
import { fixture, readJson } from "./helpers";

type Pt = [number, number];

const ORIENTATIONS = ["landscape", "portrait", "square"] as const;

const still = (o: (typeof ORIENTATIONS)[number]) => readJson<RenderProps>("tests", "fixtures", "still", `props.${o}.json`);

/** Every player and the ball pulled towards the centre of the frame's pitch, to crowd them further. */
function crowded(p: RenderProps, f: number): RenderProps {
  const q = JSON.parse(JSON.stringify(p)) as RenderProps;
  const pull = (x: number, c: number) => Math.round(c + (x - c) * f);
  for (const t of Object.values(q.tracks.players)) {
    t[0] = pull(t[0]!, 5250);
    t[1] = pull(t[1]!, 3400);
  }
  q.tracks.ball[0] = pull(q.tracks.ball[0]!, 5250);
  q.tracks.ball[1] = pull(q.tracks.ball[1]!, 3400);
  for (const o of q.overlays) {
    if ("static" in o.geom) o.geom.static = o.geom.static.map(([x, y]) => [pull(x * 100, 5250) / 100, pull(y * 100, 3400) / 100]);
  }
  return q;
}

const rectHitsCircle = (b: Rect, x: number, y: number, r: number) => {
  const dx = Math.max(b.x0 - x, 0, x - b.x1);
  const dy = Math.max(b.y0 - y, 0, y - b.y1);
  return Math.hypot(dx, dy) < r;
};

const rectsHit = (a: Rect, b: Rect) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

function segHitsCircle(a: Pt, b: Pt, x: number, y: number, r: number): boolean {
  const vx = b[0] - a[0];
  const vy = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((x - a[0]) * vx + (y - a[1]) * vy) / (vx * vx + vy * vy || 1)));
  return Math.hypot(a[0] + t * vx - x, a[1] + t * vy - y) < r;
}

function segHitsRect(a: Pt, b: Pt, rect: Rect): boolean {
  for (let i = 0; i <= 64; i++) {
    const x = a[0] + ((b[0] - a[0]) * i) / 64;
    const y = a[1] + ((b[1] - a[1]) * i) / 64;
    if (x > rect.x0 && x < rect.x1 && y > rect.y0 && y < rect.y1) return true;
  }
  return false;
}

/** Everything a label on this still is covering or crossing, as readable strings (empty = clean). */
function overlaps(p: RenderProps): string[] {
  const out: string[] = [];
  const labels = placePlayerLabels(p, 0);
  const cam = cameraAt(p, 0);
  const r = tokenRadiusPx(cam.w, p.width, p.height, p.orientation);
  const u = Math.min(p.width, p.height) / 1080;
  const s = pxPerMetre(cam.w, p.width, p.height, p.orientation);
  const rings = p.overlays.flatMap((o) => (o.kind === "ring" ? overlayPoints(o, 0) : []));
  const ringPx = rings.map(([x, y]) => worldToScreen(x, y, cam, p.width, p.height, p.orientation));
  const tokens = screenTokens(p, 0);
  const b = ballAt(p, 0)!;
  const [bx, by] = worldToScreen(b[0], b[1], cam, p.width, p.height, p.orientation);
  const bR = ballRadiusPx(s, u);
  const rail = p.principleRail?.rect;
  for (const [i, l] of labels.entries()) {
    if (l.x0 < 0 || l.y0 < 0 || l.x1 > p.width || l.y1 > p.height) out.push(`${l.text} leaves the frame`);
    if (rail && rectsHit(l, { x0: rail[0], y0: rail[1], x1: rail[2], y1: rail[3] })) out.push(`${l.text} on the key panel`);
    if (rectHitsCircle(l, bx, by, bR)) out.push(`${l.text} on the ball`);
    if (l.leader && segHitsCircle(l.leader[0], l.leader[1], bx, by, bR)) out.push(`${l.text} leader on the ball`);
    for (const t of tokens) {
      if (rectHitsCircle(l, t.x, t.y, r)) out.push(`${l.text} on token ${t.e.id}`);
      if (l.leader && t.e.id !== l.id && segHitsCircle(l.leader[0], l.leader[1], t.x, t.y, r)) out.push(`${l.text} leader on token ${t.e.id}`);
    }
    for (const [x, y] of ringPx) {
      if (rectHitsCircle(l, x, y, ringOuterRadiusPx(r, u))) out.push(`${l.text} on a ring at ${x | 0},${y | 0}`);
    }
    for (const [j, m] of labels.entries()) {
      if (j > i && rectsHit(l, m)) out.push(`${l.text} on ${m.text}`);
      if (j !== i && l.leader && segHitsRect(l.leader[0], l.leader[1], m)) out.push(`${l.text} leader on ${m.text}`);
    }
  }
  return out;
}

describe("still labels (durationInFrames = 1)", () => {
  it("the checks catch the reported overlaps when labels stay below their tokens", () => {
    const found = overlaps({ ...still("landscape"), durationInFrames: 2 });
    expect(found).toContain("BARNABÁS VARGA on token A8");
    expect(found).toContain("EDUARDO CAMAVINGA on token H10");
  });

  describe.each(ORIENTATIONS)("%s", (o) => {
    it("the dense fixture has a label for every player and no overlap of any kind", () => {
      const p = still(o);
      expect(placePlayerLabels(p, 0).length).toBe(22);
      expect(overlaps(p)).toEqual([]);
    });

    it("stays clean when the players crowd in further", () => {
      for (const f of [0.95, 0.9, 0.85, 0.8, 0.75]) expect(overlaps(crowded(still(o), f)), `pulled in x${f}`).toEqual([]);
    });

    it("is deterministic", () => {
      expect(placePlayerLabels(still(o), 0)).toEqual(placePlayerLabels(still(o), 0));
    });
  });

  it("the reported cases: neither label of the Varga / Bernardo Silva pair covers the holder or the ball", () => {
    const p = still("landscape");
    const labels = placePlayerLabels(p, 0);
    const holder = screenTokens(p, 0).find((t) => t.e.number === 20)!;
    const cam = cameraAt(p, 0);
    const ring = ringOuterRadiusPx(tokenRadiusPx(cam.w, p.width, p.height, p.orientation), 1);
    const [bx, by] = worldToScreen(p.tracks.ball[0]! / 100, p.tracks.ball[1]! / 100, cam, p.width, p.height, p.orientation);
    for (const name of ["BARNABÁS VARGA", "BERNARDO SILVA", "EDUARDO CAMAVINGA", "LUKA JOVIĆ"]) {
      const l = labels.find((x) => x.text === name)!;
      expect(rectHitsCircle(l, holder.x, holder.y, ring), name).toBe(false);
      expect(rectHitsCircle(l, bx, by, 8), name).toBe(false);
    }
  });

  it("the ball sits fully outside the holder's token and ring, clear of every other token", () => {
    for (const o of ORIENTATIONS) {
      const p = still(o);
      const cam = cameraAt(p, 0);
      const r = tokenRadiusPx(cam.w, p.width, p.height, p.orientation);
      const u = Math.min(p.width, p.height) / 1080;
      const bR = ballRadiusPx(pxPerMetre(cam.w, p.width, p.height, p.orientation), u);
      const [bx, by] = worldToScreen(p.tracks.ball[0]! / 100, p.tracks.ball[1]! / 100, cam, p.width, p.height, p.orientation);
      const nearest = Math.min(...screenTokens(p, 0).map((t) => Math.hypot(t.x - bx, t.y - by)));
      expect(nearest, o).toBeGreaterThanOrEqual(ringOuterRadiusPx(r, u) + bR);
    }
  });

  it("a player with no name gets no label but still pushes the others away", () => {
    const p = still("landscape");
    const named = p.entities.find((e) => e.number === 20)!;
    named.label = null;
    const labels = placePlayerLabels(p, 0);
    expect(labels.length).toBe(21);
    expect(labels.some((l) => l.id === named.id)).toBe(false);
    expect(overlaps(p)).toEqual([]);
  });

  it("no names at all draws nothing", () => {
    const p = still("landscape");
    for (const e of p.entities) e.label = null;
    expect(placePlayerLabels(p, 0)).toEqual([]);
  });
});

describe("video labels (durationInFrames > 1) keep the fixed slot", () => {
  const named = (): RenderProps => {
    const p = fixture();
    for (const e of p.entities) e.label = `Player Number ${e.number}`;
    return p;
  };

  it("every label is exactly where it always was, straight below its token, at every frame", () => {
    const p = named();
    for (const frame of [0, 10, 45, 89]) {
      const labels = placePlayerLabels(p, frame);
      const tokens = screenTokens(p, frame).filter((t) => t.e.label);
      expect(labels.map((l) => l.id)).toEqual(tokens.map((t) => t.e.id));
      const r = tokenRadiusPx(cameraAt(p, frame).w, p.width, p.height, p.orientation);
      const fs = Math.max(19, r * 0.6);
      for (const [i, l] of labels.entries()) {
        const t = tokens[i]!;
        const text = t.e.label!.toUpperCase();
        const w = estimateTextWidth(text, fs, "title", 0.04) + 16;
        expect(l.leader).toBeNull();
        expect(l.text).toBe(text);
        expect(l.fontSize).toBe(fs);
        expect(l.x0).toBeCloseTo(t.x - w / 2, 9);
        expect(l.x1).toBeCloseTo(t.x + w / 2, 9);
        expect(l.y0).toBeCloseTo(t.y + r * 1.08, 9);
        expect(l.y1 - l.y0).toBeCloseTo(fs * 1.15 + 6, 9);
      }
    }
  });

  it("does not move a label away from a neighbour: overlaps in motion are left alone rather than jumping", () => {
    const p = named();
    const a = p.tracks.players.H1!;
    const b = p.tracks.players.H2!;
    for (let i = 0; i < a.length; i++) b[i] = a[i]! + (i % 2 === 0 ? 120 : 0);
    const labels = placePlayerLabels(p, 45);
    const la = labels.find((l) => l.id === "H1")!;
    const lb = labels.find((l) => l.id === "H2")!;
    expect(rectsHit(la, lb)).toBe(true);
    expect(la.y0).toBeCloseTo(lb.y0, 9);
  });
});
