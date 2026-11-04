// Where the player name pills go, as a pure function of (props, frame).
//
// Video: always straight below the token. Players move, and a pill that changed side from frame to frame or scene to
// scene would be worse than a passing overlap, so video keeps one fixed slot.
// One-frame still (durationInFrames === 1): nothing moves, so the whole set is solved at once. Every pill must clear
// every token and ring (its own too), the ball, every other pill and the key panel. A pill stays against its token
// when it can and takes a leader line when the crowd leaves no room there. The search counts nodes rather than time,
// so a still rendered twice comes out the same.
import type { Entity, RenderProps } from "../generated/render_props";
import type { P2 } from "./geometry";
import { estimateTextWidth, unit, type Rect } from "./layout";
import { overlayPoints, ringOuterRadiusPx } from "./overlays";
import { ballRadiusPx, pxPerMetre, tokenRadiusPx, worldToScreen } from "./projection";
import { ballAt, cameraAt, playerAt } from "./tracks";

export interface ScreenToken {
  e: Entity;
  x: number;
  y: number;
}

/** Tokens on (or near) the screen at `frame`, in draw order: away first so home sits on top. */
export function screenTokens(p: RenderProps, frame: number): ScreenToken[] {
  const cam = cameraAt(p, frame);
  const r = tokenRadiusPx(cam.w, p.width, p.height, p.orientation);
  const ordered = [...p.entities].sort((a, b) => (a.team === b.team ? 0 : a.team === "A" ? -1 : 1));
  const out: ScreenToken[] = [];
  for (const e of ordered) {
    const pos = playerAt(p, e.id, frame);
    if (!pos) continue;
    const [x, y] = worldToScreen(pos[0], pos[1], cam, p.width, p.height, p.orientation);
    if (x < -3 * r || y < -3 * r || x > p.width + 3 * r || y > p.height + 3 * r) continue;
    out.push({ e, x, y });
  }
  return out;
}

export interface PlacedLabel extends Rect {
  id: string;
  team: Entity["team"];
  text: string;
  fontSize: number;
  /** token edge to pill, when the pill had to move away from its token */
  leader: [P2, P2] | null;
}

interface Size {
  text: string;
  fontSize: number;
  w: number;
  h: number;
}

function pillSize(label: string, r: number, u: number): Size {
  const text = label.toUpperCase();
  const fontSize = Math.max(19 * u, r * 0.6);
  return { text, fontSize, w: estimateTextWidth(text, fontSize, "title", 0.04) + 2 * 8 * u, h: fontSize * 1.15 + 6 * u };
}

export function placePlayerLabels(p: RenderProps, frame: number): PlacedLabel[] {
  const tokens = screenTokens(p, frame);
  const labelled = tokens.filter((t) => t.e.label);
  if (labelled.length === 0) return [];
  const cam = cameraAt(p, frame);
  const r = tokenRadiusPx(cam.w, p.width, p.height, p.orientation);
  const u = unit(p.width, p.height);
  if (p.durationInFrames === 1) return solveStill(p, frame, tokens, labelled, r, u);
  return labelled.map((t) => {
    const size = pillSize(t.e.label!, r, u);
    const top = t.y + r * 1.08;
    return { id: t.e.id, team: t.e.team, text: size.text, fontSize: size.fontSize, x0: t.x - size.w / 2, y0: top, x1: t.x + size.w / 2, y1: top + size.h, leader: null };
  });
}

// ---- still solver --------------------------------------------------------------------------------------------------

interface Circle {
  x: number;
  y: number;
  r: number;
  /** token this circle belongs to (its own leader may start inside it) */
  id: string | null;
}

interface Candidate extends Rect {
  cost: number;
  leader: [P2, P2] | null;
}

const HARD = 1e6;
const NODE_LIMIT = 40_000;

const rectsOverlap = (a: Rect, b: Rect, pad = 0) => a.x0 < b.x1 + pad && b.x0 < a.x1 + pad && a.y0 < b.y1 + pad && b.y0 < a.y1 + pad;

function rectHitsCircle(b: Rect, c: Circle): boolean {
  const dx = Math.max(b.x0 - c.x, 0, c.x - b.x1);
  const dy = Math.max(b.y0 - c.y, 0, c.y - b.y1);
  return dx * dx + dy * dy < c.r * c.r;
}

function segHitsCircle([a, b]: [P2, P2], c: Circle): boolean {
  const vx = b[0] - a[0];
  const vy = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((c.x - a[0]) * vx + (c.y - a[1]) * vy) / (vx * vx + vy * vy || 1)));
  return Math.hypot(a[0] + t * vx - c.x, a[1] + t * vy - c.y) < c.r;
}

function segHitsRect([a, b]: [P2, P2], rect: Rect): boolean {
  // Liang-Barsky clip of the segment against the box
  const vx = b[0] - a[0];
  const vy = b[1] - a[1];
  let t0 = 0;
  let t1 = 1;
  for (const [d, q] of [[-vx, a[0] - rect.x0], [vx, rect.x1 - a[0]], [-vy, a[1] - rect.y0], [vy, rect.y1 - a[1]]] as const) {
    if (d === 0) {
      if (q < 0) return false;
    } else {
      const t = q / d;
      if (d < 0) t0 = Math.max(t0, t);
      else t1 = Math.min(t1, t);
      if (t0 > t1) return false;
    }
  }
  return true;
}

function segsCross([a, b]: [P2, P2], [c, d]: [P2, P2]): boolean {
  const side = (p: P2, q: P2, s: P2) => (q[0] - p[0]) * (s[1] - p[1]) - (q[1] - p[1]) * (s[0] - p[0]);
  return side(a, b, c) * side(a, b, d) < 0 && side(c, d, a) * side(c, d, b) < 0;
}

/** Slots around a token, cheapest first. `clear` is the radius the pill has to stay outside. */
function slots(t: ScreenToken, size: Size, clear: number, u: number): Candidate[] {
  const { w, h } = size;
  const c = clear + 3 * u;
  const d = c * Math.SQRT1_2;
  const out: Candidate[] = [];
  const add = (cx: number, cy: number, cost: number, far: boolean) => {
    const box = { x0: cx - w / 2, y0: cy - h / 2, x1: cx + w / 2, y1: cy + h / 2 };
    let leader: [P2, P2] | null = null;
    if (far) {
      const nx = Math.max(box.x0, Math.min(t.x, box.x1));
      const ny = Math.max(box.y0, Math.min(t.y, box.y1));
      const len = Math.hypot(nx - t.x, ny - t.y) || 1;
      leader = [[t.x + ((nx - t.x) / len) * clear, t.y + ((ny - t.y) / len) * clear], [nx, ny]];
    }
    out.push({ ...box, cost, leader });
  };
  // against the token: under it, over it (sliding sideways along the ring), beside it, off its diagonals
  for (const [dir, side] of [[1, 0], [-1, 0.7]] as const) {
    for (const [f, slide] of [[0, 0], [0.25, 0.3], [-0.25, 0.3], [0.5, 0.6], [-0.5, 0.6]] as const) add(t.x + f * w, t.y + dir * (c + h / 2), side + slide, false);
  }
  for (const dir of [1, -1]) add(t.x + dir * (c + w / 2), t.y, 1.5, false);
  for (const dx of [1, -1]) for (const dy of [1, -1]) add(t.x + dx * (d + w / 2), t.y + dy * (d + h / 2), 1.8, false);
  // further out, tied to the token by a leader line
  for (let k = 1; k <= 4; k++) {
    const step = k * (h + 6 * u);
    const reach = k * 26 * u;
    for (const dir of [1, -1]) {
      for (const f of [0, 0.5, -0.5]) add(t.x + f * w, t.y + dir * (c + step + h / 2), 4 * k + Math.abs(f), true);
      add(t.x + dir * (c + reach + w / 2), t.y, 4 * k + 0.2, true);
      for (const dy of [1, -1]) add(t.x + dir * (d + reach + w / 2), t.y + dy * (d + reach + h / 2), 4 * k + 0.4, true);
    }
  }
  return out;
}

function pairConflict(a: Candidate, b: Candidate, pad: number): number {
  let n = rectsOverlap(a, b, pad) ? 1 : 0;
  if (a.leader && segHitsRect(a.leader, b)) n++;
  if (b.leader && segHitsRect(b.leader, a)) n++;
  if (a.leader && b.leader && segsCross(a.leader, b.leader)) n++;
  return n;
}

/** Bounding box of everything a label's candidates could cover: labels further apart than this can never clash. */
function reachOf(list: Candidate[]): Rect {
  const box = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  for (const c of list) {
    const pts: P2[] = [[c.x0, c.y0], [c.x1, c.y1], ...(c.leader ?? [])];
    for (const [x, y] of pts) {
      box.x0 = Math.min(box.x0, x);
      box.y0 = Math.min(box.y0, y);
      box.x1 = Math.max(box.x1, x);
      box.y1 = Math.max(box.y1, y);
    }
  }
  return box;
}

/**
 * Candidate index per label: no clash between any two if that can be found, and the lowest total slot cost among those.
 * `cands` are sorted by cost. A local descent gives a first answer; a bounded search with forward checking
 * (most constrained label first, dropping every slot the choice rules out) then looks for better.
 */
function assign(cands: Candidate[][], pad: number): number[] {
  const n = cands.length;
  const reach = cands.map(reachOf);
  const near = cands.map((_, i) => cands.map((_, j) => j).filter((j) => j !== i && rectsOverlap(reach[i]!, reach[j]!, pad)));
  const cur = cands.map(() => 0);
  for (let sweep = 0; sweep < 20; sweep++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      let bestA = cur[i]!;
      let bestScore = Infinity;
      cands[i]!.forEach((ca, a) => {
        let score = ca.cost;
        for (const j of near[i]!) score += pairConflict(ca, cands[j]![cur[j]!]!, pad) * HARD;
        if (score < bestScore) {
          bestScore = score;
          bestA = a;
        }
      });
      if (bestA !== cur[i]) {
        cur[i] = bestA;
        moved = true;
      }
    }
    if (!moved) break;
  }
  let best = cur.slice();
  let bestCost = 0;
  for (let i = 0; i < n; i++) {
    bestCost += cands[i]![cur[i]!]!.cost;
    for (const j of near[i]!) if (j > i) bestCost += pairConflict(cands[i]![cur[i]!]!, cands[j]![cur[j]!]!, pad) * HARD;
  }
  const picks = cur.slice();
  const open = cands.map(() => true);
  let nodes = 0;
  const search = (domains: number[][], left: number, cost: number): void => {
    if (nodes++ > NODE_LIMIT) return;
    if (left === 0) {
      if (cost < bestCost) {
        bestCost = cost;
        best = picks.slice();
      }
      return;
    }
    let bound = cost;
    let i = -1;
    for (let j = 0; j < n; j++) {
      if (!open[j]) continue;
      bound += cands[j]![domains[j]![0]!]!.cost;
      if (i < 0 || domains[j]!.length < domains[i]!.length) i = j;
    }
    const others = bound - cands[i]![domains[i]![0]!]!.cost;
    open[i] = false;
    for (const a of domains[i]!) {
      const ca = cands[i]![a]!;
      if (others + ca.cost >= bestCost) break; // sorted by cost: every later slot is dearer still
      const next = domains.slice();
      let dead = false;
      for (const j of near[i]!) {
        if (!open[j]) continue;
        const kept = domains[j]!.filter((b) => pairConflict(ca, cands[j]![b]!, pad) === 0);
        if (kept.length === 0) {
          dead = true;
          break;
        }
        next[j] = kept;
      }
      if (dead) continue;
      picks[i] = a;
      search(next, left - 1, cost + ca.cost);
    }
    open[i] = true;
  };
  search(cands.map((list) => list.map((_, a) => a)), n, 0);
  return best;
}

function solveStill(p: RenderProps, frame: number, tokens: ScreenToken[], labelled: ScreenToken[], r: number, u: number): PlacedLabel[] {
  const cam = cameraAt(p, frame);
  const s = pxPerMetre(cam.w, p.width, p.height, p.orientation);
  const ringR = ringOuterRadiusPx(r, u);
  const ringPts: P2[] = [];
  for (const o of p.overlays) {
    if (o.kind !== "ring" || frame < o.from || frame >= o.to) continue;
    for (const [x, y] of overlayPoints(o, frame)) ringPts.push(worldToScreen(x, y, cam, p.width, p.height, p.orientation));
  }
  // what a pill must stay off: tokens and rings (a ring on a token widens that token's circle), and the ball
  const clearOf = (t: ScreenToken) => (ringPts.some(([x, y]) => Math.hypot(x - t.x, y - t.y) < r) ? ringR : r + 2 * u);
  const circles: Circle[] = tokens.map((t) => ({ x: t.x, y: t.y, r: clearOf(t) + 2 * u, id: t.e.id }));
  for (const [x, y] of ringPts) {
    if (!tokens.some((t) => Math.hypot(x - t.x, y - t.y) < r)) circles.push({ x, y, r: ringR + 2 * u, id: null });
  }
  const ball = ballAt(p, frame);
  if (ball) {
    const [x, y] = worldToScreen(ball[0], ball[1], cam, p.width, p.height, p.orientation);
    circles.push({ x, y, r: ballRadiusPx(s, u) + 4 * u, id: null });
  }
  const rect = p.principleRail?.rect;
  const rail: Rect | null = rect ? { x0: rect[0], y0: rect[1], x1: rect[2], y1: rect[3] } : null;
  const edge = 6 * u;
  const staticHits = (t: ScreenToken, c: Candidate) => {
    let hits = 0;
    if (c.x0 < edge || c.y0 < edge || c.x1 > p.width - edge || c.y1 > p.height - edge) hits++;
    if (rail && rectsOverlap(c, rail, edge)) hits++;
    for (const o of circles) {
      if (rectHitsCircle(c, o)) hits++;
      if (c.leader && o.id !== t.e.id && segHitsCircle(c.leader, o)) hits++;
    }
    return hits;
  };
  const sizes = labelled.map((t) => pillSize(t.e.label!, r, u));
  const cands = labelled.map((t, i) => {
    const all = slots(t, sizes[i]!, clearOf(t), u);
    const free = all.filter((c) => staticHits(t, c) === 0);
    // Nothing free: keep every slot, charged for what it covers, so the least bad one wins.
    const usable = free.length > 0 ? free : all.map((c) => ({ ...c, cost: c.cost + staticHits(t, c) * HARD }));
    return usable.sort((a, b) => a.cost - b.cost);
  });
  const picks = assign(cands, 3 * u);
  return labelled.map((t, i) => {
    const c = cands[i]![picks[i]!]!;
    return { id: t.e.id, team: t.e.team, text: sizes[i]!.text, fontSize: sizes[i]!.fontSize, x0: c.x0, y0: c.y0, x1: c.x1, y1: c.y1, leader: c.leader };
  });
}
