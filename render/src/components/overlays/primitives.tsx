import React from "react";
import { TITLE_STACK } from "../../fonts";
import { pathD, pointAt, polyLength, subPath, type P2 } from "../../lib/geometry";
import { clampBox, estimateTextWidth, type Rect } from "../../lib/layout";

export interface StrokePathProps {
  pts: P2[];
  color: string;
  width: number;
  /** [dash, gap] in px; undefined = solid */
  dash?: [number, number];
  drawFrom: number;
  drawTo: number;
  /** arrowhead length in px (0 = none) */
  arrow?: number;
  glowId?: string;
  /** extra width of the casing stroke drawn under the line (0 = none) */
  casing?: number;
  casingColor?: string;
}

/**
 * A screen-space polyline revealed between drawFrom..drawTo of its length. The draw-on truncates the sampled path at
 * progress x path length (so dashed strokes draw on correctly); stroke-dashoffset keeps the dash phase locked to the
 * path start while it draws. Optional arrowhead rides the drawn tip.
 */
export const StrokePath: React.FC<StrokePathProps> = ({
  pts,
  color,
  width,
  dash,
  drawFrom,
  drawTo,
  arrow = 0,
  glowId,
  casing = 0,
  casingColor = "rgba(0,0,0,0.35)",
}) => {
  if (pts.length < 2) return null;
  const L = polyLength(pts);
  const l0 = drawFrom * L;
  const l1 = drawTo * L;
  if (l1 - l0 < 0.5) return null;
  const head = arrow > 0 ? Math.min(arrow, (l1 - l0) * 0.9) : 0;
  const shaftEnd = head > 0 ? Math.max(l0, l1 - head * 0.72) : l1;
  const shaft = subPath(pts, l0, shaftEnd);
  const d = shaft.length >= 2 ? pathD(shaft) : "";
  const dashProps = dash
    ? { strokeDasharray: `${dash[0].toFixed(2)} ${dash[1].toFixed(2)}`, strokeDashoffset: (l0 % (dash[0] + dash[1])).toFixed(2) }
    : {};
  let headPoly = "";
  if (head > 0) {
    const { p, angle } = pointAt(pts, l1);
    const hw = head * 0.5;
    const bx = p[0] - Math.cos(angle) * head;
    const by = p[1] - Math.sin(angle) * head;
    const nx = -Math.sin(angle) * hw;
    const ny = Math.cos(angle) * hw;
    headPoly = `${p[0].toFixed(2)},${p[1].toFixed(2)} ${(bx + nx).toFixed(2)},${(by + ny).toFixed(2)} ${(bx - nx).toFixed(2)},${(by - ny).toFixed(2)}`;
  }
  return (
    <g>
      {glowId ? (
        <g filter={`url(#${glowId})`} opacity={0.55}>
          {d ? <path d={d} fill="none" stroke={color} strokeWidth={width * 2.2} strokeLinecap="round" strokeLinejoin="round" /> : null}
          {headPoly ? <polygon points={headPoly} fill={color} stroke={color} strokeWidth={width} strokeLinejoin="round" /> : null}
        </g>
      ) : null}
      {casing > 0 && d ? (
        <path
          d={d}
          fill="none"
          stroke={casingColor}
          strokeWidth={width + casing}
          strokeLinecap="round"
          strokeLinejoin="round"
          {...dashProps}
        />
      ) : null}
      {d ? <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" {...dashProps} /> : null}
      {casing > 0 && headPoly ? <polygon points={headPoly} fill="none" stroke={casingColor} strokeWidth={Math.max(1, width * 0.35) + casing} strokeLinejoin="round" /> : null}
      {headPoly ? (
        <polygon
          points={headPoly}
          fill={color}
          stroke={color}
          strokeWidth={Math.max(1, width * 0.35)}
          strokeLinejoin="round"
        />
      ) : null}
    </g>
  );
};

export interface PillProps {
  /** anchor: centre of the box */
  cx: number;
  cy: number;
  text: string;
  bg: string;
  fg: string;
  fontSize: number;
  safe: Rect;
  border?: string;
  u: number;
  bgOpacity?: number;
  /** uppercase the text (default true; false keeps units such as "m") */
  upper?: boolean;
}

/** Size of a Pill box in px (text width is a deterministic over-estimate, so text never overflows the box). */
export function pillBox(text: string, fontSize: number, u: number, upper = true): { w: number; h: number } {
  const padX = 14 * u;
  const padY = 7 * u;
  const w = estimateTextWidth(text, fontSize, "title", 0.05, upper) + 2 * padX;
  const h = fontSize * 1.08 + 2 * padY;
  return { w, h };
}

/** Condensed label box centred on (cx, cy), kept fully inside the safe area. */
export const Pill: React.FC<PillProps> = ({ cx, cy, text, bg, fg, fontSize, safe, border, u, bgOpacity = 0.94, upper = true }) => {
  const { w, h } = pillBox(text, fontSize, u, upper);
  const [x, y] = clampBox(cx - w / 2, cy - h / 2, w, h, safe);
  return (
    <g>
      <rect x={x + 2 * u} y={y + 3 * u} width={w} height={h} rx={6 * u} fill="#000000" opacity={0.28} />
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={6 * u}
        fill={bg}
        fillOpacity={bgOpacity}
        stroke={border ?? "none"}
        strokeWidth={border ? 2 * u : 0}
      />
      <text
        x={x + w / 2}
        y={y + h / 2 + fontSize * 0.36}
        textAnchor="middle"
        fontFamily={TITLE_STACK}
        fontWeight={800}
        fontSize={fontSize}
        letterSpacing="0.05em"
        fill={fg}
      >
        {upper ? text.toUpperCase() : text}
      </text>
    </g>
  );
};
