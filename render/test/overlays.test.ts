import { describe, expect, it } from "vitest";
import type { Overlay } from "../src/generated/render_props";
import { animState, inProgress, isVisible, outRemaining, pulsePhase } from "../src/lib/anim";
import { catmullRom, clipPolygonToRect, pointAt, polyLength, polygonCentroid, subPath, type P2 } from "../src/lib/geometry";
import { areaAnchor, chooseAreaLabelUV, choosePathSlot, visibleArea } from "../src/lib/labels";
import { hudRects, pauseBadgeRect } from "../src/lib/hud";
import { playerAt, cameraAt } from "../src/lib/tracks";
import { tokenRadiusPx, worldToScreen } from "../src/lib/projection";
import { safeArea } from "../src/lib/layout";
import { distanceText, overlayPoints, OVER_KINDS, UNDER_KINDS } from "../src/lib/overlays";
import { contrastRatio, pitchCasing, readableOn, resolveColor } from "../src/lib/colors";
import { fixture } from "./helpers";

const ov = (id: string): Overlay => fixture().overlays.find((o) => o.id === id)!;

describe("overlay visibility windows", () => {
  it("is half-open [from, to) for every fixture overlay", () => {
    for (const o of fixture().overlays) {
      expect(isVisible(o, o.from - 1)).toBe(false);
      expect(isVisible(o, o.from)).toBe(true);
      expect(isVisible(o, o.to - 1)).toBe(true);
      expect(isVisible(o, o.to)).toBe(false);
      expect(animState(o, o.to).visible).toBe(false);
    }
  });
  it("draw-in reveals the run arrow over inAnim.frames (N01: from 5, draw 10)", () => {
    const o = ov("N01");
    expect(animState(o, 4).visible).toBe(false);
    const s5 = animState(o, 5);
    expect(s5.visible).toBe(true);
    expect(s5.drawTo).toBeGreaterThan(0);
    expect(s5.drawTo).toBeLessThan(0.05);
    expect(animState(o, 9).drawTo).toBeLessThan(animState(o, 10).drawTo);
    expect(animState(o, 14).drawTo).toBeCloseTo(1, 12);
    expect(animState(o, 30)).toMatchObject({ drawFrom: 0, drawTo: 1, opacity: 1, scale: 1 });
  });
  it("fade-out ends N01 over its last 8 frames", () => {
    const o = ov("N01"); // to 70, fade 8
    expect(animState(o, 61).opacity).toBe(1);
    expect(animState(o, 62).opacity).toBeCloseTo(1, 12);
    expect(animState(o, 66).opacity).toBeLessThan(animState(o, 63).opacity);
    expect(animState(o, 69).opacity).toBeGreaterThan(0);
    expect(outRemaining(o, 69)).toBeCloseTo(1 / 8, 12);
  });
  it("pop scales in with overshoot then settles (N02)", () => {
    const o = ov("N02"); // from 60, pop 8
    const scales = [60, 61, 62, 63, 64, 65, 66, 67, 68].map((f) => animState(o, f).scale);
    expect(Math.max(...scales)).toBeGreaterThan(1);
    expect(scales[scales.length - 1]).toBeCloseTo(1, 12);
    expect(inProgress(o, 67)).toBe(1);
  });
  it("draw-out erases from the start", () => {
    const o: Overlay = { ...ov("N05"), outAnim: { anim: "draw", frames: 10 } };
    const s = animState(o, o.to - 5);
    expect(s.drawFrom).toBeGreaterThan(0);
    expect(s.drawTo).toBe(1);
  });
  it("anim none / 0 frames is instant", () => {
    const o: Overlay = { ...ov("N05"), inAnim: { anim: "none", frames: 0 }, outAnim: { anim: "fade", frames: 0 } };
    expect(animState(o, o.from)).toMatchObject({ opacity: 1, scale: 1, drawTo: 1 });
    expect(animState(o, o.to - 1)).toMatchObject({ opacity: 1 });
  });
  it("pulse is a pure function of the frame", () => {
    expect(pulsePhase(0, 36)).toBe(0);
    expect(pulsePhase(18, 36)).toBe(0.5);
    expect(pulsePhase(36 + 9, 36)).toBe(0.25);
  });
});

describe("overlay geometry", () => {
  it("static geometry is constant; perFrame is indexed by frame - from and clamped", () => {
    const o = ov("N01");
    expect(overlayPoints(o, 30)).toEqual([[38, 50], [39.4, 44.5], [40, 39]]);
    const pf: Overlay = { ...o, from: 10, to: 13, geom: { perFrame: [[[1, 1]], [[2, 2]], [[3, 3]]] } };
    expect(overlayPoints(pf, 10)).toEqual([[1, 1]]);
    expect(overlayPoints(pf, 12)).toEqual([[3, 3]]);
    expect(overlayPoints(pf, 99)).toEqual([[3, 3]]);
  });
  it("distance text is computed from the points", () => {
    expect(distanceText([[0, 0], [3, 4]], null)).toBe("5.0 m");
    expect(distanceText([[10, 10], [22.3, 10]], "Gap")).toBe("Gap · 12.3 m");
  });
  it("every kind has a layer and colours resolve from the theme", () => {
    const kinds: Overlay["kind"][] = ["run_arrow", "pass_line", "zone", "line", "ring", "spotlight", "label", "distance", "polygon"];
    for (const k of kinds) expect(UNDER_KINDS.has(k) || OVER_KINDS.has(k)).toBe(true);
    const t = fixture().theme;
    expect(resolveColor(t, "H")).toBe(t.teams.H.fill);
    expect(resolveColor(t, "A")).toBe(t.teams.A.fill);
    expect(resolveColor(t, "accent")).toBe(t.accent);
    expect(resolveColor(t, "warn")).toBe(t.warn);
    expect(resolveColor(t, "ink")).toBe(t.ink);
  });
  it("run arrow casing keeps a team colour legible on the grass", () => {
    const GRASS = "#1f5f2c";
    const dark = "rgba(0,0,0,0.5)";
    const light = "rgba(255,255,255,0.85)";
    for (const stands of ["#f5f5f5", "#f2c80f", "#ffffff"]) expect(pitchCasing(stands, GRASS).color).toBe(dark);
    for (const close of ["#00843d", "#1d428a", "#c8102e", "#111111", GRASS]) expect(pitchCasing(close, GRASS).color).toBe(light);
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 6);
    expect(contrastRatio(GRASS, GRASS)).toBe(1);
    expect(readableOn("#ffffff", "#000000", "#ffffff")).toBe("#000000");
    expect(readableOn("#000000", "#000000", "#ffffff")).toBe("#ffffff");
  });
  it("curved paths pass through every control point; draw-on sub-paths have the right length", () => {
    const pts: P2[] = [[0, 0], [100, 50], [200, 0]];
    const c = catmullRom(pts, 3);
    for (const p of pts) expect(c.some((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < 1e-9)).toBe(true);
    const L = polyLength(c);
    expect(polyLength(subPath(c, 0, L * 0.4))).toBeCloseTo(L * 0.4, 6);
    expect(pointAt([[0, 0], [10, 0]], 5).p).toEqual([5, 0]);
  });
  it("polygon clipping and centroid", () => {
    const sq: P2[] = [[-10, -10], [10, -10], [10, 10], [-10, 10]];
    const clipped = clipPolygonToRect(sq, 0, 0, 100, 100);
    expect(polygonCentroid(clipped)[0]).toBeCloseTo(5, 9);
    expect(polygonCentroid(clipped)[1]).toBeCloseTo(5, 9);
  });
});

describe("label placement", () => {
  it("is deterministic and keeps the zone label on the visible zone, inside the safe area, off tokens and HUD", () => {
    const p = fixture();
    const o = ov("N04"); // zone 30..90 while the camera zooms in and the freeze badge shows (75..82)
    const [bw, bh] = [300, 46];
    const uv = chooseAreaLabelUV(o, p, bw, bh);
    expect(chooseAreaLabelUV(o, p, bw, bh)).toEqual(uv);
    const safe = safeArea(p.width, p.height);
    let covered = 0;
    for (let f = o.from; f < o.to; f++) {
      const c = areaAnchor(o, p, f, uv, bw, bh);
      expect(c, `frame ${f}`).not.toBeNull();
      const [x, y] = c!;
      expect(x - bw / 2).toBeGreaterThanOrEqual(safe.x0 - 1e-6);
      expect(x + bw / 2).toBeLessThanOrEqual(safe.x1 + 1e-6);
      expect(y - bh / 2).toBeGreaterThanOrEqual(safe.y0 - 1e-6);
      expect(y + bh / 2).toBeLessThanOrEqual(safe.y1 + 1e-6);
      expect(visibleArea(o, p, f, bw, bh)).not.toBeNull();
      for (const h of hudRects(p, f)) {
        const overlap = x + bw / 2 > h.x0 && x - bw / 2 < h.x1 && y + bh / 2 > h.y0 && y - bh / 2 < h.y1;
        expect(overlap, `frame ${f} label overlaps HUD`).toBe(false);
      }
      const cam = cameraAt(p, f);
      const r = tokenRadiusPx(cam.w, p.width, p.height, p.orientation);
      const hit = p.entities.some((e) => {
        const pos = playerAt(p, e.id, f)!;
        const [tx, ty] = worldToScreen(pos[0], pos[1], cam, p.width, p.height, p.orientation);
        const dx = Math.max(Math.abs(tx - x) - bw / 2, 0);
        const dy = Math.max(Math.abs(ty - y) - bh / 2, 0);
        return dx * dx + dy * dy < r * r;
      });
      if (hit) covered++;
    }
    // the zone is crowded (players on and inside it), so allow a few grazing frames, but no more than 10%
    expect(covered).toBeLessThanOrEqual(Math.floor((o.to - o.from) / 10));
    expect(pauseBadgeRect(1920, 1080).x1).toBeCloseTo(safe.x1, 9);
  });
  it("path labels pick a stable slot", () => {
    const p = fixture();
    const o: Overlay = { ...ov("N01"), label: "Underlap" };
    expect(choosePathSlot(o, p, true, 200, 46)).toBe(choosePathSlot(o, p, true, 200, 46));
  });
});
