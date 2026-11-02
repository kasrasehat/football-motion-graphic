// Screen-space geometry helpers (px). Curves are emitted as dense polylines so that the drawn path, its length
// (for stroke-dashoffset draw-on) and the arrowhead placement all come from the same deterministic samples.

export type P2 = [number, number];

export const dist = (a: P2, b: P2): number => Math.hypot(b[0] - a[0], b[1] - a[1]);

/** Centripetal Catmull-Rom spline through all points (no cusps / self-loops), sampled every ~`stepPx`. */
export function catmullRom(points: P2[], stepPx = 3): P2[] {
  if (points.length < 3) return points.slice();
  const out: P2[] = [];
  const pts: P2[] = [
    extrapolate(points[1]!, points[0]!),
    ...points,
    extrapolate(points[points.length - 2]!, points[points.length - 1]!),
  ];
  for (let i = 1; i < pts.length - 2; i++) {
    const p0 = pts[i - 1]!;
    const p1 = pts[i]!;
    const p2 = pts[i + 1]!;
    const p3 = pts[i + 2]!;
    const t0 = 0;
    const t1 = t0 + Math.max(Math.sqrt(dist(p0, p1)), 1e-6);
    const t2 = t1 + Math.max(Math.sqrt(dist(p1, p2)), 1e-6);
    const t3 = t2 + Math.max(Math.sqrt(dist(p2, p3)), 1e-6);
    const n = Math.min(400, Math.max(8, Math.ceil(dist(p1, p2) / stepPx)));
    for (let k = 0; k < n; k++) {
      const t = t1 + ((t2 - t1) * k) / n;
      out.push(crPoint(p0, p1, p2, p3, t0, t1, t2, t3, t));
    }
  }
  out.push(points[points.length - 1]!);
  return out;
}

function extrapolate(a: P2, b: P2): P2 {
  return [2 * b[0] - a[0], 2 * b[1] - a[1]];
}

function lerp2(a: P2, b: P2, ta: number, tb: number, t: number): P2 {
  const d = tb - ta;
  const u = d === 0 ? 0 : (t - ta) / d;
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
}

function crPoint(p0: P2, p1: P2, p2: P2, p3: P2, t0: number, t1: number, t2: number, t3: number, t: number): P2 {
  const a1 = lerp2(p0, p1, t0, t1, t);
  const a2 = lerp2(p1, p2, t1, t2, t);
  const a3 = lerp2(p2, p3, t2, t3, t);
  const b1 = lerp2(a1, a2, t0, t2, t);
  const b2 = lerp2(a2, a3, t1, t3, t);
  return lerp2(b1, b2, t1, t2, t);
}

export function cumulative(pts: P2[]): number[] {
  const acc: number[] = [0];
  for (let i = 1; i < pts.length; i++) acc.push(acc[i - 1]! + dist(pts[i - 1]!, pts[i]!));
  return acc;
}

export function polyLength(pts: P2[]): number {
  const c = cumulative(pts);
  return c[c.length - 1] ?? 0;
}

/** Point and screen angle (radians) at arc length `len` along the polyline. */
export function pointAt(pts: P2[], len: number): { p: P2; angle: number } {
  if (pts.length === 0) return { p: [0, 0], angle: 0 };
  if (pts.length === 1) return { p: pts[0]!, angle: 0 };
  const c = cumulative(pts);
  const total = c[c.length - 1]!;
  const L = Math.max(0, Math.min(len, total));
  let i = 1;
  while (i < pts.length - 1 && c[i]! < L) i++;
  const a = pts[i - 1]!;
  const b = pts[i]!;
  const seg = c[i]! - c[i - 1]!;
  const u = seg > 0 ? (L - c[i - 1]!) / seg : 0;
  return { p: [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u], angle: Math.atan2(b[1] - a[1], b[0] - a[0]) };
}

/** The sub-polyline between arc lengths [l0, l1]. */
export function subPath(pts: P2[], l0: number, l1: number): P2[] {
  if (pts.length < 2 || l1 <= l0) return [];
  const c = cumulative(pts);
  const out: P2[] = [pointAt(pts, l0).p];
  for (let i = 1; i < pts.length - 1; i++) if (c[i]! > l0 && c[i]! < l1) out.push(pts[i]!);
  out.push(pointAt(pts, l1).p);
  return out;
}

export function pathD(pts: P2[], close = false): string {
  if (pts.length === 0) return "";
  const f = (v: number) => (Math.round(v * 100) / 100).toString();
  let d = `M${f(pts[0]![0])} ${f(pts[0]![1])}`;
  for (let i = 1; i < pts.length; i++) d += `L${f(pts[i]![0])} ${f(pts[i]![1])}`;
  return close ? d + "Z" : d;
}

/** Sutherland-Hodgman clip of a polygon to an axis-aligned rectangle. */
export function clipPolygonToRect(poly: P2[], x0: number, y0: number, x1: number, y1: number): P2[] {
  type Edge = (p: P2) => boolean;
  type Cut = (a: P2, b: P2) => P2;
  const cutX = (x: number): Cut => (a, b) => [x, a[1] + ((b[1] - a[1]) * (x - a[0])) / (b[0] - a[0])];
  const cutY = (y: number): Cut => (a, b) => [a[0] + ((b[0] - a[0]) * (y - a[1])) / (b[1] - a[1]), y];
  const edges: [Edge, Cut][] = [
    [(p) => p[0] >= x0, cutX(x0)],
    [(p) => p[0] <= x1, cutX(x1)],
    [(p) => p[1] >= y0, cutY(y0)],
    [(p) => p[1] <= y1, cutY(y1)],
  ];
  let out = poly.slice();
  for (const [inside, cut] of edges) {
    const input = out;
    out = [];
    for (let i = 0; i < input.length; i++) {
      const cur = input[i]!;
      const prev = input[(i + input.length - 1) % input.length]!;
      if (inside(cur)) {
        if (!inside(prev)) out.push(cut(prev, cur));
        out.push(cur);
      } else if (inside(prev)) {
        out.push(cut(prev, cur));
      }
    }
    if (out.length === 0) break;
  }
  return out;
}

/** Area centroid of a simple polygon (falls back to the vertex mean for degenerate input). */
export function polygonCentroid(poly: P2[]): P2 {
  let a = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i]!;
    const q = poly[(i + 1) % poly.length]!;
    const cr = p[0] * q[1] - q[0] * p[1];
    a += cr;
    cx += (p[0] + q[0]) * cr;
    cy += (p[1] + q[1]) * cr;
  }
  if (Math.abs(a) < 1e-9) {
    const n = Math.max(1, poly.length);
    return [poly.reduce((s, p) => s + p[0], 0) / n, poly.reduce((s, p) => s + p[1], 0) / n];
  }
  return [cx / (3 * a), cy / (3 * a)];
}
