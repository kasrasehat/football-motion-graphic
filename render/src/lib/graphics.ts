// Pure helpers for the match-preview data graphics (components/graphics/*): orientation-aware layout, reveal
// gating, rounding, lenient parsing of `graphics[].data` and text fitting. No React, no frame state: everything here
// is a pure function and is covered by render/test/graphics.test.ts.
import type { Theme } from "../generated/render_props";
import { easeOutCubic } from "./anim";
import { contrastRatio, mix, rgba, withHsl } from "./colors";
import { estimateTextWidth, safeArea, unit, type Rect } from "./layout";

// ---------------------------------------------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------------------------------------------

export type LayoutMode = "landscape" | "portrait" | "square";

export function layoutMode(width: number, height: number): LayoutMode {
  if (width >= height * 1.2) return "landscape";
  if (height >= width * 1.2) return "portrait";
  return "square";
}

/** The lower part of the frame that graphics keep clear of essential content (captions live there). */
export const CAPTION_CLEAR_FRACTION = 0.22;

/** Where a graphic may put essential content: the 90% safe area minus the caption band at the bottom. */
export function contentRect(width: number, height: number): Rect {
  const s = safeArea(width, height);
  return { x0: s.x0, y0: s.y0, x1: s.x1, y1: Math.min(s.y1, height * (1 - CAPTION_CLEAR_FRACTION)) };
}

/** Panel chrome sizes at 1080p (multiplied by unit()). */
export const SHELL_1080 = { padX: 44, padTop: 30, padBottom: 34, kicker: 24, title: 58, ruleGap: 24, accent: 8 };

export interface ShellLayout {
  u: number;
  mode: LayoutMode;
  /** the panel, in frame px */
  panel: Rect;
  /** the body box inside the panel, in frame px (templates lay out relative to its top-left) */
  body: Rect;
  bodyW: number;
  bodyH: number;
  /** largest body height the frame allows for this panel */
  maxBodyH: number;
  headerH: number;
  padX: number;
}

/** Height of the panel header (accent strip, kicker line, title line, gap) in px. */
export function shellHeaderH(u: number): number {
  const s = SHELL_1080;
  return (s.padTop + s.kicker * 1.25 + s.title * 1.05 + s.ruleGap) * u;
}

/**
 * Panel geometry for a full-screen data card: centred horizontally, centred vertically inside contentRect().
 * `panelW` defaults to 1560 px (landscape, at 1080p) or the full content width; `bodyH` defaults to the maximum.
 */
export function shellLayout(width: number, height: number, opts: { panelW?: number; bodyH?: number } = {}): ShellLayout {
  const u = unit(width, height);
  const mode = layoutMode(width, height);
  const c = contentRect(width, height);
  const maxW = c.x1 - c.x0;
  const pw = Math.min(maxW, opts.panelW ?? (mode === "landscape" ? 1560 * u : maxW));
  const headerH = shellHeaderH(u);
  const padX = SHELL_1080.padX * u;
  const padBottom = SHELL_1080.padBottom * u;
  const maxBodyH = Math.max(0, c.y1 - c.y0 - headerH - padBottom);
  const want = opts.bodyH === undefined || !Number.isFinite(opts.bodyH) ? maxBodyH : opts.bodyH;
  const bodyH = Math.max(0, Math.min(maxBodyH, want));
  const ph = headerH + bodyH + padBottom;
  const x0 = (width - pw) / 2;
  const y0 = c.y0 + (c.y1 - c.y0 - ph) / 2;
  const panel = { x0, y0, x1: x0 + pw, y1: y0 + ph };
  const body = { x0: x0 + padX, y0: y0 + headerH, x1: x0 + pw - padX, y1: y0 + headerH + bodyH };
  return { u, mode, panel, body, bodyW: body.x1 - body.x0, bodyH, maxBodyH, headerH, padX };
}

/** Evenly divide `total` px into `n` cells separated by `gap`; returns [start, size] per cell. */
export function splitEven(total: number, n: number, gap: number): [number, number][] {
  if (n <= 0) return [];
  const size = Math.max(0, (total - gap * (n - 1)) / n);
  return Array.from({ length: n }, (_, i) => [i * (size + gap), size] as [number, number]);
}

// ---------------------------------------------------------------------------------------------------------------
// Reveals: `reveals[i].frame` are ABSOLUTE frames. Item/group i appears at reveal i; items beyond the last reveal
// appear with the last one; with no reveals everything enters from `from`, staggered.
// ---------------------------------------------------------------------------------------------------------------

export const REVEAL_STAGGER = 6;
export const REVEAL_FRAMES = 12;

export interface RevealSource {
  from: number;
  reveals: ReadonlyArray<{ frame: number }>;
}

/** Absolute frame at which item (or group) `index` starts to appear. Never earlier than `from`. */
export function revealFrame(g: RevealSource, index: number, stagger = REVEAL_STAGGER): number {
  const rs = Array.isArray(g.reveals) ? g.reveals : [];
  const i = Math.max(0, Math.floor(index));
  if (rs.length === 0) return g.from + i * stagger;
  const r = rs[Math.min(i, rs.length - 1)];
  const f = r && typeof r.frame === "number" && Number.isFinite(r.frame) ? r.frame : g.from;
  return Math.max(g.from, f);
}

/** 0 before `at`; eases to 1 over `frames` (already > 0 on frame `at` itself). */
export function revealProgress(frame: number, at: number, frames = REVEAL_FRAMES): number {
  if (frame < at) return 0;
  return easeOutCubic((frame - at + 1) / Math.max(1, frames));
}

// ---------------------------------------------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------------------------------------------

export function asNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Integers as-is; otherwise up to 2 decimals (1 from 10, 0 from 100), trailing zeros trimmed. */
export function formatNumber(n: number): string {
  const a = Math.abs(n);
  const d = Number.isInteger(n) ? 0 : a >= 100 ? 0 : a >= 10 ? 1 : 2;
  let s = n.toFixed(d);
  if (d > 0) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s === "-0" ? "0" : s;
}

/** Printed stat value: numbers formatted (+ unit; "%" attaches directly), strings verbatim, missing -> en dash. */
export function formatValue(v: unknown, unitStr?: unknown): string {
  const n = asNumber(v);
  if (n === null) return typeof v === "string" && v.trim() !== "" ? v.trim() : "–";
  const s = formatNumber(n);
  const u = typeof unitStr === "string" ? unitStr.trim() : "";
  if (!u) return s;
  return /^[%‰°]/.test(u) ? s + u : `${s} ${u}`;
}

/** Bar lengths for one mirrored row: each numeric value / max of the pair (>= 0); non-numbers get no bar (null). */
export function barFractions(h: unknown, a: unknown): [number | null, number | null] {
  const hn = asNumber(h);
  const an = asNumber(a);
  const hv = hn === null ? null : Math.max(0, hn);
  const av = an === null ? null : Math.max(0, an);
  const m = Math.max(hv ?? 0, av ?? 0);
  const f = (v: number | null): number | null => (v === null ? null : m > 0 ? v / m : 0);
  return [f(hv), f(av)];
}

/**
 * Bar lengths for a "lower is better" row such as a league position: the better (smaller) value gets the full bar
 * and the other `best / value`, so 1st v 2nd reads as 1 v 0.5. Non-numbers and values <= 0 get no bar (null).
 */
export function rankFractions(h: unknown, a: unknown): [number | null, number | null] {
  const pos = (v: unknown): number | null => {
    const n = asNumber(v);
    return n !== null && n > 0 ? n : null;
  };
  const hv = pos(h);
  const av = pos(a);
  const best = Math.min(hv ?? Infinity, av ?? Infinity);
  const f = (v: number | null): number | null => (v === null ? null : best / v);
  return [f(hv), f(av)];
}

/** Per-row "lower is better" flags of a stat_compare (`lower_better[]`, set by the props builder for rank keys). */
export function lowerBetterFlags(v: unknown, n: number): boolean[] {
  const a = Array.isArray(v) ? v : [];
  return Array.from({ length: n }, (_, i) => a[i] === true);
}

/** English ordinal of a positive integer rank ("1st", "17th", "22nd"); anything else -> null. */
export function ordinal(v: unknown): string | null {
  const n = asNumber(v);
  if (n === null || !Number.isInteger(n) || n <= 0) return null;
  const t = n % 100;
  const s = t >= 11 && t <= 13 ? "th" : n % 10 === 1 ? "st" : n % 10 === 2 ? "nd" : n % 10 === 3 ? "rd" : "th";
  return `${n}${s}`;
}

/** Contrast a team fill must reach against the card surface to read as a filled shape (WCAG non-text contrast). */
export const CARD_FILL_MIN_CONTRAST = 3;

/** The colour graphics are drawn on: the top of the panel gradient in `Shell` (the darker bottom differs by < 5%). */
export function cardSurface(theme: Theme): string {
  return mix(theme.panel, theme.ink, 0.05);
}

/**
 * A colour for a team fill drawn on `bg` that reads at `min`:1 contrast: the primary if it does, else the
 * secondary if that does, else the primary moved toward whichever of white/black contrasts more with `bg`, in 5%
 * steps until it does (keeps the hue, so the team stays recognisable).
 */
export function contrastSafeFill(primary: string, secondary: string, bg: string, min = CARD_FILL_MIN_CONTRAST): string {
  if (contrastRatio(primary, bg) >= min) return primary;
  if (contrastRatio(secondary, bg) >= min) return secondary;
  const to = contrastRatio("#ffffff", bg) >= contrastRatio("#000000", bg) ? "#ffffff" : "#000000";
  for (let i = 1; i <= 20; i++) {
    const c = mix(primary, to, i * 0.05);
    if (contrastRatio(c, bg) >= min) return c;
  }
  return to;
}

/** A team's fill as drawn on a data card (bars, segments, swatches, chips): `contrastSafeFill` of fill / ring. */
export function cardTeamFill(theme: Theme, side: "H" | "A"): string {
  const t = theme.teams[side];
  return contrastSafeFill(t.fill, t.ring, cardSurface(theme));
}

/** Text colour on `cardTeamFill`: the kit's own text colour when the fill is the kit's, else black or white, whichever reads. */
export function cardTeamInk(theme: Theme, side: "H" | "A"): string {
  const t = theme.teams[side];
  const fill = cardTeamFill(theme, side);
  if (fill === t.fill) return t.text;
  return contrastRatio(fill, "#ffffff") >= contrastRatio(fill, "#111111") ? "#ffffff" : "#111111";
}

/**
 * Outline for a kit-coloured shape that keeps the real kit fill (jersey, token): the kit's ring colour when the fill
 * or the ring stands off the card, else a light (or dark) edge so the shape never disappears into the card.
 */
export function kitOutline(theme: Theme, side: "H" | "A"): string {
  const t = theme.teams[side];
  const bg = cardSurface(theme);
  if (contrastRatio(t.fill, bg) >= CARD_FILL_MIN_CONTRAST || contrastRatio(t.ring, bg) >= CARD_FILL_MIN_CONTRAST) return t.ring;
  return contrastRatio("#ffffff", bg) >= contrastRatio("#000000", bg) ? rgba("#ffffff", 0.85) : rgba("#000000", 0.7);
}

/** Empty bar track on a card: faint fill plus a hairline edge, so an empty slot never reads as a filled one. */
export function cardTrack(theme: Theme, u: number): { background: string; boxShadow: string } {
  return { background: rgba(theme.ink, 0.06), boxShadow: `inset 0 0 0 ${Math.max(1, 1.5 * u)}px ${rgba(theme.ink, 0.14)}` };
}

/**
 * Largest-remainder (Hamilton) rounding: integers proportional to `values` that sum exactly to `total`.
 * Non-numbers and negatives count as 0; ties go to the earlier index. All-zero input returns all zeros.
 */
export function largestRemainder(values: ReadonlyArray<unknown>, total = 100): number[] {
  const v = values.map((x) => {
    const n = asNumber(x);
    return n !== null && n > 0 ? n : 0;
  });
  const sum = v.reduce((s, x) => s + x, 0);
  const T = Math.max(0, Math.round(total));
  if (sum <= 0 || T === 0) return v.map(() => 0);
  const exact = v.map((x) => (x / sum) * T);
  const out = exact.map((e) => Math.floor(e));
  let rem = T - out.reduce((s, x) => s + x, 0);
  const order = exact.map((e, i) => ({ i, r: e - Math.floor(e) })).sort((a, b) => b.r - a.r || a.i - b.i);
  for (let k = 0; rem > 0 && order.length > 0; k = (k + 1) % order.length, rem--) out[order[k]!.i]! += 1;
  return out;
}

/** "11.0%" style probability text (p in 0..1), en dash when missing. */
export function percentText(p: unknown, decimals = 1): string {
  const n = asNumber(p);
  return n === null ? "–" : `${(Math.max(0, n) * 100).toFixed(decimals)}%`;
}

// ---------------------------------------------------------------------------------------------------------------
// Pattern rows: counts out of each row's own sample, from one team's split record. Nothing here rounds or prints a
// percentage; the fraction only sizes a bar.
// ---------------------------------------------------------------------------------------------------------------

/** A count out of its sample, or null when the sample is 0, the data is missing, or the two cannot both be true. */
export type PatternCell = { count: number; sample: number; fraction: number; text: string } | null;

const isCount = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

export function patternCell(count: unknown, sample: unknown): PatternCell {
  if (!isCount(count) || !isCount(sample) || sample === 0 || count > sample) return null;
  return { count, sample, fraction: count / sample, text: `${count} of ${sample}` };
}

const field = (v: unknown, key: string): unknown => (v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>)[key] : undefined);

/** Sum of half-time/full-time cells; one missing cell makes the whole sum unknown, not a smaller number. */
function htFtCell(split: unknown, keys: ReadonlyArray<string>): PatternCell {
  const cells = keys.map((k) => field(field(split, "ht_ft"), k));
  if (!cells.every(isCount)) return null;
  return patternCell((cells as number[]).reduce((s, n) => s + n, 0), field(split, "ht_ft_sample"));
}

/** Each row reads one team's split record. ht_ft keys are half-time result / full-time result, relative to that team. */
const PATTERN_ROWS: ReadonlyArray<{ label: string; cell: (split: unknown) => PatternCell }> = [
  { label: "Both teams scored", cell: (s) => patternCell(field(field(s, "btts"), "yes"), field(s, "played")) },
  { label: "Over 2.5 goals", cell: (s) => patternCell(field(field(field(s, "goal_lines"), "2.5"), "over"), field(s, "played")) },
  { label: "Led at half-time", cell: (s) => htFtCell(s, ["W/W", "W/D", "W/L"]) },
  { label: "Won from behind at half-time", cell: (s) => htFtCell(s, ["L/W"]) },
  { label: "Dropped points after leading at half-time", cell: (s) => htFtCell(s, ["W/D", "W/L"]) },
];

export interface PatternRow {
  label: string;
  home: PatternCell;
  away: PatternCell;
}

export function patternRows(home: unknown, away: unknown): PatternRow[] {
  return PATTERN_ROWS.map((r) => ({ label: r.label, home: r.cell(home), away: r.cell(away) }));
}

// ---------------------------------------------------------------------------------------------------------------
// Crests
// ---------------------------------------------------------------------------------------------------------------

const CREST_URI = /^data:image\/(png|svg\+xml);base64,/;

/** The team's crest, only as an embedded image: anything else (absent, or a URL that would need fetching) is null. */
export function teamCrest(theme: Theme, side: "H" | "A"): string | null {
  const c = theme.teams[side].crest;
  return typeof c === "string" && CREST_URI.test(c) ? c : null;
}

// ---------------------------------------------------------------------------------------------------------------
// Results, scores, dates, team names
// ---------------------------------------------------------------------------------------------------------------

export type FormResult = "W" | "D" | "L";

/** ["W","d","L"] or "WWDLW" -> results; anything else is dropped. */
export function normResults(v: unknown): FormResult[] {
  const raw: unknown[] = typeof v === "string" ? Array.from(v) : Array.isArray(v) ? v : [];
  const out: FormResult[] = [];
  for (const x of raw) {
    if (typeof x !== "string") continue;
    const c = x.trim().charAt(0).toUpperCase();
    if (c === "W" || c === "D" || c === "L") out.push(c);
  }
  return out;
}

/** League points: W = 3, D = 1, L = 0. */
export function formPoints(rs: ReadonlyArray<FormResult>): number {
  return rs.reduce((s, r) => s + (r === "W" ? 3 : r === "D" ? 1 : 0), 0);
}

/** Semantic result colours derived from the theme: win = vivid grass hue, draw = neutral grey, loss = warn. */
export function resultColors(theme: Theme): Record<FormResult, string> {
  return { W: withHsl(theme.pitch.grass, 0.62, 0.4), D: mix(theme.ink, theme.panel, 0.52), L: theme.warn };
}

/** "2-1" / "2–1" / "2:1" -> [2, 1]; anything else -> null. */
export function parseScore(s: unknown): [number, number] | null {
  if (typeof s !== "string") return null;
  const m = /^\s*(\d{1,2})\s*[-–—:x]\s*(\d{1,2})\s*$/.exec(s);
  return m ? [Number(m[1]), Number(m[2])] : null;
}

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

/** "2024-03-12" -> {day: "12 MAR", year: "2024", full: "12 MAR 2024"} (string parsing only; no clock). */
export function formatMatchDay(iso: unknown): { day: string; year: string; full: string } {
  const s = typeof iso === "string" ? iso.trim() : "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  const mon = m ? MONTHS[Number(m[2]) - 1] : undefined;
  if (!m || !mon) return { day: s, year: "", full: s };
  const day = `${Number(m[3])} ${mon}`;
  return { day, year: m[1]!, full: `${day} ${m[1]}` };
}

/** Lower-case, accents stripped, punctuation collapsed ("Atlético  Madrid" -> "atletico madrid"). */
export function normName(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Which theme team a free-text team name refers to (exact name/short match, then containment), else null. */
export function teamSide(name: unknown, theme: Theme): "H" | "A" | null {
  if (typeof name !== "string") return null;
  const n = normName(name);
  if (!n) return null;
  const sides = ["H", "A"] as const;
  for (const side of sides) {
    const t = theme.teams[side];
    if (n === normName(t.name) || n === normName(t.short)) return side;
  }
  for (const side of sides) {
    const tn = normName(theme.teams[side].name);
    if (tn.length >= 4 && n.length >= 4 && (n.includes(tn) || tn.includes(n))) return side;
  }
  return null;
}

// ---------------------------------------------------------------------------------------------------------------
// Line-ups
// ---------------------------------------------------------------------------------------------------------------

export type Position = "G" | "D" | "M" | "F";

export interface LineupPlayer {
  name: string;
  number: number | null;
  position: Position;
  /** tactic-spec line (0 = keeper) and team-normalized y, present when the engine matched the player to the spec */
  line?: number;
  y?: number;
}

const POS_ORDER: Record<Position, number> = { G: 0, D: 1, M: 2, F: 3 };

export function normPosition(v: unknown): Position {
  const s = typeof v === "string" ? v.trim().toUpperCase() : "";
  if (s === "G" || s === "GK" || s.startsWith("GOAL")) return "G";
  if (s === "D" || s.startsWith("DEF") || s === "CB" || s === "LB" || s === "RB") return "D";
  if (s === "F" || s === "FW" || s.startsWith("FOR") || s.startsWith("ATT") || s === "ST") return "F";
  return "M";
}

/** Lenient list of players (objects with a name; at most `max`). */
export function normLineup(v: unknown, max = 11): LineupPlayer[] {
  if (!Array.isArray(v)) return [];
  const out: LineupPlayer[] = [];
  for (const x of v) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    const name = typeof o.name === "string" ? o.name.trim() : "";
    const num = asNumber(o.number);
    const line = asNumber(o.line);
    const y = asNumber(o.y);
    out.push({ name, number: num === null ? null : Math.round(num), position: normPosition(o.position), ...(line !== null && y !== null ? { line, y } : {}) });
    if (out.length >= max) break;
  }
  return out;
}

/** "4-2-3-1" -> [4, 2, 3, 1] (2..6 lines of 1..6 players), else null. */
export function parseFormation(v: unknown): number[] | null {
  if (typeof v !== "string") return null;
  const s = v.trim();
  if (!/^\d(\s*[-–]\s*\d){1,5}$/.test(s)) return null;
  const parts = s.split(/\s*[-–]\s*/).map(Number);
  return parts.every((n) => n >= 1 && n <= 6) ? parts : null;
}

/** Split a row longer than `max` into balanced consecutive rows (6 -> 3+3, 7 -> 4+3). */
export function splitRow<T>(row: T[], max = 5): T[][] {
  if (row.length <= max) return [row];
  const n = Math.ceil(row.length / max);
  const base = Math.floor(row.length / n);
  const extra = row.length % n;
  const out: T[][] = [];
  let k = 0;
  for (let i = 0; i < n; i++) {
    const size = base + (i < extra ? 1 : 0);
    out.push(row.slice(k, k + size));
    k += size;
  }
  return out;
}

/** Rows from the tactic spec, when every player has a line and y: one per line, each ordered by y (smallest first). */
function specRows(players: ReadonlyArray<LineupPlayer>): LineupPlayer[][] | null {
  if (players.length === 0 || players.some((p) => p.line === undefined || p.y === undefined)) return null;
  const lines = Array.from(new Set(players.map((p) => p.line))).sort((a, b) => a! - b!);
  return lines.map((l) => players.filter((p) => p.line === l).sort((a, b) => a.y! - b.y!));
}

/**
 * Token rows from the goalkeeper (index 0) to the most advanced line, each row from the viewer's left to right. Rows
 * follow the tactic spec when the props carry it. Otherwise the formation is used when it accounts for every outfield
 * player, else the position counts (G, D, M, F), long rows split at 5.
 */
export function lineupRows(players: ReadonlyArray<LineupPlayer>, formation?: unknown): LineupPlayer[][] {
  const fromSpec = specRows(players);
  if (fromSpec) return fromSpec;
  const sorted = players
    .map((p, i) => ({ p, i }))
    .sort((a, b) => POS_ORDER[a.p.position] - POS_ORDER[b.p.position] || a.i - b.i)
    .map((x) => x.p);
  const gk = sorted.length > 0 && sorted[0]!.position === "G" ? [sorted[0]!] : [];
  const outfield = sorted.slice(gk.length);
  const rows: LineupPlayer[][] = gk.length ? [gk] : [];
  const f = parseFormation(formation);
  if (f && f.reduce((s, n) => s + n, 0) === outfield.length) {
    let k = 0;
    for (const n of f) {
      rows.push(outfield.slice(k, k + n));
      k += n;
    }
    return rows;
  }
  for (const pos of ["G", "D", "M", "F"] as const) {
    const row = outfield.filter((p) => p.position === pos);
    if (row.length) rows.push(...splitRow(row, 5));
  }
  return rows;
}

// ---------------------------------------------------------------------------------------------------------------
// Scoreline grid
// ---------------------------------------------------------------------------------------------------------------

const COUNT_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"];

/** The heat grid only has values for the listed scorelines; this note stops its empty cells reading as zero. */
export function scoreGridNote(listed: number): string {
  return `${COUNT_WORDS[listed] ?? listed} likeliest scores only`;
}

// ---------------------------------------------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------------------------------------------

type Family = "body" | "title";

/** Cut `text` with an ellipsis so its estimated width fits maxWidth. */
export function ellipsize(text: string, maxWidth: number, fontSize: number, family: Family = "body", ls = 0, upper = false): string {
  if (estimateTextWidth(text, fontSize, family, ls, upper) <= maxWidth) return text;
  const chars = Array.from(text);
  for (let n = chars.length - 1; n > 0; n--) {
    const t = `${chars.slice(0, n).join("").trimEnd()}…`;
    if (estimateTextWidth(t, fontSize, family, ls, upper) <= maxWidth) return t;
  }
  return "…";
}

/**
 * Greedy word wrap using the generous width estimates, so the browser never needs more room than this.
 * Text past `maxLines` is cut with an ellipsis on the last line, and `cut` is true.
 */
export function wrapText(text: string, maxWidth: number, fontSize: number, maxLines = 2, family: Family = "body"): { lines: string[]; cut: boolean } {
  const lines: string[] = [];
  let cur = "";
  for (const word of text.trim().split(/\s+/).filter(Boolean)) {
    const next = cur ? `${cur} ${word}` : word;
    if (cur && estimateTextWidth(next, fontSize, family) > maxWidth) {
      lines.push(cur);
      cur = word;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return { lines, cut: false };
  const rest = lines.slice(maxLines - 1).join(" ");
  return { lines: [...lines.slice(0, maxLines - 1), ellipsize(rest, maxWidth, fontSize, family)], cut: true };
}

/** Largest size in [min, size] at which no text needs more than `maxLines`; `min` when some text never fits. */
export function fitWrappedSize(texts: ReadonlyArray<string>, maxWidth: number, size: number, min: number, maxLines = 2, family: Family = "body"): number {
  const step = (size - min) / 20;
  for (let s = size; step > 0 && s > min; s -= step) {
    if (texts.every((t) => !wrapText(t, maxWidth, s, maxLines, family).cut)) return s;
  }
  return Math.min(size, min);
}

export interface NewsRowLayout {
  rowH: number;
  /** scale of the row against its ideal height */
  k: number;
  iconS: number;
  textX: number;
  nameFs: number;
  nameLine: number;
  reasonW: number;
  reasonFs: number;
  reasonLine: number;
}

export const NEWS_REASON_LINES = 2;
const NEWS_REASON_LH = 1.18;

/**
 * team_news row metrics at 1080p x `u`. Rows grow when a reason needs a second line; reasons sit under the name and the
 * status pill so they get the full text width, in one shared size. `maxRowH` is the most the panel can give each row.
 */
export function newsRowLayout(reasons: ReadonlyArray<string>, colW: number, maxRowH: number, u: number): NewsRowLayout {
  const twoLines = reasons.some((r) => wrapText(r, colW - 60 * u, 23 * u, 1).cut);
  const ideal = (twoLines ? 96 : 80) * u;
  const rowH = Math.min(ideal, maxRowH);
  const k = Math.min(1, rowH / ideal);
  const iconS = 42 * u * Math.max(0.75, k);
  const textX = iconS + 18 * u;
  const reasonW = colW - textX;
  const nameFs = 30 * u * k;
  const nameLine = nameFs * 1.2;
  const room = (rowH - 4 * u - nameLine) / ((twoLines ? NEWS_REASON_LINES : 1) * NEWS_REASON_LH);
  const reasonFs = fitWrappedSize(reasons, reasonW, Math.min(23 * u, room), 18 * u, NEWS_REASON_LINES);
  return { rowH, k, iconS, textX, nameFs, nameLine, reasonW, reasonFs, reasonLine: reasonFs * NEWS_REASON_LH };
}

const PARTICLE =/^(de|da|di|do|dos|das|del|della|van|von|der|den|le|la|el|al|ter|ten|mac|st\.?)$/i;
const SUFFIX = /^(jr\.?|junior|júnior|sr\.?|ii|iii|iv|neto|filho)$/i;

/** Shirt-style short name: last word, keeping particles ("de Jong") and suffixes ("Vinicius Jr."). */
export function surname(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return parts.join("");
  let i = parts.length - 1;
  if (SUFFIX.test(parts[i]!) && i > 0) i--;
  while (i > 0 && PARTICLE.test(parts[i - 1]!)) i--;
  return parts.slice(i).join(" ");
}

/** Ever shorter ways to print a player's name: full, surname, and the known-as name before a suffix. */
export function nameCandidates(name: string): string[] {
  const full = name.trim().replace(/\s+/g, " ");
  const parts = full.split(" ").filter(Boolean);
  const out = [full, surname(full)];
  if (parts.length > 1 && SUFFIX.test(parts[parts.length - 1]!)) out.push(parts[parts.length - 2]!);
  return out.filter((s, i) => s !== "" && out.indexOf(s) === i);
}

/**
 * The first name candidate whose (generous) width estimate fits, else the shortest candidate. Callers render it in a
 * box with CSS `text-overflow: ellipsis`, so a candidate that still does not fit is cut with an ellipsis there.
 */
export function fitName(name: string, maxWidth: number, fontSize: number, family: Family = "title", ls = 0, upper = false): string {
  const cands = nameCandidates(name);
  for (const c of cands) if (estimateTextWidth(c, fontSize, family, ls, upper) <= maxWidth) return c;
  return cands[cands.length - 1] ?? "";
}

/**
 * The label for a team beside its flag in a `w`-wide slot: the full name if it fits at `min` x `size` (the smallest a
 * `Txt` shrinks to), else the short code, so a team name is never cut to "MANCHES...".
 */
export function teamLabel(theme: Theme, side: "H" | "A", w: number, size: number, ls = 0, min = 0.72): string {
  const t = theme.teams[side];
  if (estimateTextWidth(t.name.toUpperCase(), size * min, "title", ls) <= w) return t.name;
  return t.short || t.name;
}
