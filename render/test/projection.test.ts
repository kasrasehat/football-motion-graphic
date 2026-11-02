import { describe, expect, it } from "vitest";
import {
  pxPerMetre,
  screenAngle,
  screenToWorld,
  tokenRadiusPx,
  worldMatrix,
  worldToScreen,
  type Orientation,
} from "../src/lib/projection";
import { readJson } from "./helpers";

interface Vector {
  name: string;
  orientation: Orientation;
  width: number;
  height: number;
  camera_m: [number, number, number];
  world_m: [number, number];
  screen_px: [number, number];
  px_per_m: number;
  token_radius_px: number;
}

const doc = readJson<{ tolerance_px: number; vectors: Vector[] }>("tests", "fixtures", "projection_vectors.json");
const TOL = doc.tolerance_px;

describe("projection vectors (shared with engine/tms/render/projection.py)", () => {
  it("has >= 20 cases covering every orientation", () => {
    expect(doc.vectors.length).toBeGreaterThanOrEqual(20);
    expect(TOL).toBeLessThanOrEqual(1e-6);
    for (const o of ["landscape", "portrait", "square"]) {
      expect(doc.vectors.some((v) => v.orientation === o)).toBe(true);
    }
  });

  for (const v of doc.vectors) {
    it(v.name, () => {
      const cam = { cx: v.camera_m[0], cy: v.camera_m[1], w: v.camera_m[2] };
      const [sx, sy] = worldToScreen(v.world_m[0], v.world_m[1], cam, v.width, v.height, v.orientation);
      expect(Math.abs(sx - v.screen_px[0])).toBeLessThanOrEqual(TOL);
      expect(Math.abs(sy - v.screen_px[1])).toBeLessThanOrEqual(TOL);
      expect(Math.abs(pxPerMetre(cam.w, v.width, v.height, v.orientation) - v.px_per_m)).toBeLessThanOrEqual(TOL);
      expect(Math.abs(tokenRadiusPx(cam.w, v.width, v.height, v.orientation) - v.token_radius_px)).toBeLessThanOrEqual(TOL);
      // inverse
      const [wx, wy] = screenToWorld(sx, sy, cam, v.width, v.height, v.orientation);
      expect(Math.abs(wx - v.world_m[0])).toBeLessThan(1e-9);
      expect(Math.abs(wy - v.world_m[1])).toBeLessThan(1e-9);
      // the SVG matrix used by the pitch layer agrees with the point projection
      const [a, b, c, d, e, f] = worldMatrix(cam, v.width, v.height, v.orientation);
      const mx = a * v.world_m[0] + c * v.world_m[1] + e;
      const my = b * v.world_m[0] + d * v.world_m[1] + f;
      expect(Math.abs(mx - sx)).toBeLessThanOrEqual(TOL);
      expect(Math.abs(my - sy)).toBeLessThanOrEqual(TOL);
    });
  }
});

describe("projection semantics", () => {
  const full = { cx: 52.5, cy: 34, w: 105 };
  it("portrait: home attacks up the screen, home's right flank is screen right", () => {
    const homeGoal = worldToScreen(0, 34, full, 1080, 1920, "portrait");
    const awayGoal = worldToScreen(105, 34, full, 1080, 1920, "portrait");
    expect(homeGoal[1]).toBeGreaterThan(awayGoal[1]);
    const right = worldToScreen(52.5, 60, full, 1080, 1920, "portrait");
    const left = worldToScreen(52.5, 8, full, 1080, 1920, "portrait");
    expect(right[0]).toBeGreaterThan(left[0]);
  });
  it("w is the visible extent along pitch x", () => {
    const a = worldToScreen(52.5 - 30, 34, { cx: 52.5, cy: 34, w: 60 }, 1920, 1080, "landscape");
    const b = worldToScreen(52.5 + 30, 34, { cx: 52.5, cy: 34, w: 60 }, 1920, 1080, "landscape");
    expect(a[0]).toBeCloseTo(0, 9);
    expect(b[0]).toBeCloseTo(1920, 9);
    const top = worldToScreen(52.5 + 30, 34, { cx: 52.5, cy: 34, w: 60 }, 1080, 1920, "portrait");
    expect(top[1]).toBeCloseTo(0, 9);
  });
  it("screenAngle matches the projected direction", () => {
    for (const o of ["landscape", "portrait", "square"] as const) {
      const p0 = worldToScreen(10, 10, full, 1080, o === "portrait" ? 1920 : 1080, o);
      const p1 = worldToScreen(13, 14, full, 1080, o === "portrait" ? 1920 : 1080, o);
      expect(screenAngle(3, 4, o)).toBeCloseTo(Math.atan2(p1[1] - p0[1], p1[0] - p0[0]), 12);
    }
  });
  it("token never smaller than 26 px diameter at 1080p, 13 px at half size", () => {
    expect(tokenRadiusPx(400, 1920, 1080, "landscape")).toBeCloseTo(13, 12);
    expect(tokenRadiusPx(400, 960, 540, "landscape")).toBeCloseTo(6.5, 12);
    expect(tokenRadiusPx(60, 1920, 1080, "landscape")).toBeCloseTo(32, 12);
  });
});
