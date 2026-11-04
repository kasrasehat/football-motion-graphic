// Layout of the tactic still's key panel (principleRail), as pure functions. Sizes come from generous text-width
// estimates, so the panel the browser lays out is never taller than computed here and whole titles always fit.
import type { PrincipleRail } from "../generated/render_props";
import { estimateTextWidth, unit } from "./layout";

export const RAIL_TITLE_LS = 0.02;
export const RAIL_NAME_LS = 0.01;
export const RAIL_TITLE_LH = 1.08;
export const RAIL_NAME_LH = 1.14;
export const RAIL_BALL_LS = 0.04;
export const RAIL_BALL_LH = 1.1;
/** Gap between the items of the ball key, in chip gaps. */
export const RAIL_BALL_GAP = 1.6;

/** Size factors tried from the largest down: few principles get big type, six long ones still fit. */
const SIZE_STEPS = [1.5, 1.4, 1.3, 1.2, 1.1, 1, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5];

export interface RailMetrics {
  /** principle blocks per row: 1 in the tall landscape panel, 2 in the wide one under the pitch */
  columns: number;
  pad: number;
  colGap: number;
  rowGap: number;
  columnWidth: number;
  titleSize: number;
  lockupSize: number;
  nameSize: number;
  idWidth: number;
  chip: number;
  chipGap: number;
  ballSize: number;
  /** gap between a principle's name and its chips */
  nameGap: number;
  /** estimated height of all content, padding included (<= panel height when anything fits) */
  height: number;
}

/** Lines `text` takes when wrapped at spaces into `maxWidth`; a word wider than a line takes several. */
export function wrappedLines(text: string, maxWidth: number, size: number, family: "title" | "body", ls: number, uppercase = false): number {
  const space = estimateTextWidth(" ", size, family, ls);
  let lines = 1;
  let x = 0;
  for (const word of text.trim().split(/\s+/)) {
    const w = estimateTextWidth(word, size, family, ls, uppercase);
    if (x > 0 && x + space + w <= maxWidth) {
      x += space + w;
    } else {
      if (x > 0) lines++;
      lines += Math.max(0, Math.ceil(w / maxWidth) - 1);
      x = w > maxWidth ? w - Math.floor(w / maxWidth) * maxWidth : w;
    }
  }
  return lines;
}

export function railMetrics(rail: PrincipleRail, width: number, height: number): RailMetrics {
  const u = unit(width, height);
  const panelW = rail.rect[2] - rail.rect[0];
  const panelH = rail.rect[3] - rail.rect[1];
  const columns = panelW > 600 * u ? 2 : 1;
  const pad = 20 * u;
  const inner = panelW - 2 * pad;
  let m: RailMetrics | null = null;
  for (const k of SIZE_STEPS) {
    const colGap = 22 * u;
    const rowGap = 15 * k * u;
    const columnWidth = (inner - (columns - 1) * colGap) / columns;
    const titleSize = 31 * Math.min(k, 1.15) * u; // the title stays a heading, it does not grow into the principles' room
    const lockupSize = 24 * Math.min(k, 1.15) * u;
    const nameSize = 25 * k * u;
    const idWidth = nameSize * 1.5;
    const chip = 29 * k * u;
    const chipGap = 5 * k * u;
    const ballSize = chip * 0.62;
    const nameGap = 6 * k * u;
    const perRow = Math.max(1, Math.floor((columnWidth + chipGap) / (chip + chipGap)));
    const titleH = wrappedLines(rail.title, inner, titleSize, "title", RAIL_TITLE_LS, true) * titleSize * RAIL_TITLE_LH;
    // Lock-up and ball key: stacked in the tall panel, side by side in the wide one. The holder's name wraps if it must.
    const lockupW = 72 * u + 5.2 * lockupSize;
    const ballNameW = inner - (columns === 1 ? 0 : lockupW + colGap) - ballSize - chip - 2 * RAIL_BALL_GAP * chipGap;
    const ballLines = rail.ball.name ? wrappedLines(rail.ball.name, ballNameW, lockupSize, "title", RAIL_BALL_LS, true) : 0;
    const ballH = Math.max(chip, ballLines * lockupSize * RAIL_BALL_LH);
    const keyRows = columns === 1 ? [lockupSize * 1.2, ballH] : [Math.max(lockupSize * 1.2, ballH)];
    const keyH = keyRows.reduce((sum, row) => sum + row + rowGap * 0.7, 0);
    const blocks = rail.principles.map((pr) => {
      const lines = wrappedLines(pr.name, columnWidth - idWidth, nameSize, "title", RAIL_NAME_LS);
      const rows = Math.max(1, Math.ceil(pr.players.length / perRow));
      return lines * nameSize * RAIL_NAME_LH + nameGap + rows * chip + (rows - 1) * chipGap;
    });
    let body = 0;
    for (let i = 0; i < blocks.length; i += columns) {
      body += Math.max(...blocks.slice(i, i + columns)) + rowGap;
    }
    const total = 2 * pad + titleH + rowGap * 0.7 + keyH + rowGap * 0.7 + body;
    m = { columns, pad, colGap, rowGap, columnWidth, titleSize, lockupSize, nameSize, idWidth, chip, chipGap, ballSize, nameGap, height: total };
    if (total <= panelH) break;
  }
  return m!;
}
