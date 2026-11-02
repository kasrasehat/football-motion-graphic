import React from "react";
import type { Overlay, Pt, RenderProps, Theme } from "../../generated/render_props";
import { animState, clamp01, pulsePhase, type AnimState } from "../../lib/anim";
import { luminance, mix, readableOn, resolveColor, rgba } from "../../lib/colors";
import { catmullRom, pathD, pointAt, polyLength, subPath, type P2 } from "../../lib/geometry";
import { clampBox, estimateTextWidth } from "../../lib/layout";
import { areaAnchor, chooseAreaLabelUV, choosePathSlot, PATH_SLOTS, pathLabelOffset, pathSlotPoint } from "../../lib/labels";
import { distanceText, overlayPoints, type Layer } from "../../lib/overlays";
import { playerAt } from "../../lib/tracks";
import { TITLE_STACK } from "../../fonts";
import { useProjector, type Projector } from "../CameraRig";
import { Pill, pillBox, StrokePath } from "./primitives";

interface KindProps {
  o: Overlay;
  st: AnimState;
  /** world metres */
  world: Pt[];
  /** screen px */
  pts: P2[];
  color: string;
  theme: Theme;
  pj: Projector;
  layer: Layer;
  glowId: string;
  props: RenderProps;
  frame: number;
}

const pillFont = (pj: Projector) => 30 * pj.u;
/** Non-path overlays show a "draw" reveal as a fade (opacity itself is applied by the wrapper). */
const reveal = (st: AnimState) => clamp01(st.drawTo - st.drawFrom);

function labelPill(text: string | null, cx: number, cy: number, color: string, k: KindProps, upper = true): React.ReactNode {
  if (!text) return null;
  const fg = readableOn(color, k.theme.panel, "#ffffff");
  return <Pill cx={cx} cy={cy} text={text} bg={color} fg={fg} fontSize={pillFont(k.pj)} safe={k.pj.safe} u={k.pj.u} upper={upper} />;
}

/** Casing under a stroke: dark for light colours, a light halo for dark ones (e.g. a navy team colour on grass). */
function casingColor(color: string): string {
  return luminance(color) < 0.07 ? "rgba(255,255,255,0.55)" : "rgba(0,0,0,0.35)";
}

/** Path label beside the (unclipped) route, in the slot that covers the fewest tokens over the overlay window. */
function pathLabel(k: KindProps, curvedDefault: boolean): React.ReactNode {
  if (!k.o.label) return null;
  const curved = k.o.style.curved ?? curvedDefault;
  const path = routePoints(k, curvedDefault);
  if (path.length < 2) return null;
  const { w, h } = pillBox(k.o.label, pillFont(k.pj), k.pj.u);
  const [t, side] = PATH_SLOTS[choosePathSlot(k.o, k.props, curved, w, h)]!;
  const ang = pointAt(path, polyLength(path) * t).angle;
  const c = pathSlotPoint(path, t, side, pathLabelOffset(w, h, ang, k.pj.u));
  return c ? labelPill(k.o.label, c[0], c[1], k.color, k) : null;
}

/** True when a world point sits on (within 1 m of) any player at this frame. */
function onPlayer(k: KindProps, w: Pt): boolean {
  for (const e of k.props.entities) {
    const pos = playerAt(k.props, e.id, k.frame);
    if (pos && Math.hypot(pos[0] - w[0], pos[1] - w[1]) < 1.0) return true;
  }
  return false;
}

/** Zone / polygon label on the visible part of the area, in the slot that covers the fewest tokens / HUD boxes. */
function areaLabel(k: KindProps): React.ReactNode {
  if (!k.o.label) return null;
  const { w, h } = pillBox(k.o.label, pillFont(k.pj), k.pj.u);
  const uv = chooseAreaLabelUV(k.o, k.props, w, h);
  const c = areaAnchor(k.o, k.props, k.frame, uv, w, h);
  return c ? labelPill(k.o.label, c[0], c[1], k.color, k) : null;
}

function routePoints(k: KindProps, curvedDefault: boolean): P2[] {
  const curved = k.o.style.curved ?? curvedDefault;
  return curved && k.pts.length >= 3 ? catmullRom(k.pts, 3) : k.pts;
}

const RunArrow: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  const path = routePoints(k, true);
  if (k.layer === "over") return <>{pathLabel(k, true)}</>;
  return (
    <StrokePath
      pts={path}
      color={k.color}
      width={7 * u}
      dash={k.o.style.dash ? [20 * u, 13 * u] : undefined}
      drawFrom={k.st.drawFrom}
      drawTo={k.st.drawTo}
      arrow={30 * u}
      glowId={k.glowId}
      casing={3 * u}
      casingColor={casingColor(k.color)}
    />
  );
};

const PassLine: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  const raw = routePoints(k, false);
  // A pass runs token edge to token edge: trim ends that sit on a player so the arrowhead is not hidden under them.
  const gap = k.pj.tokenR + 4 * u;
  const a = k.world[0];
  const b = k.world[k.world.length - 1];
  const t0 = a && onPlayer(k, a) ? gap : 0;
  const t1 = b && onPlayer(k, b) ? gap : 0;
  const L = polyLength(raw);
  const path = L > t0 + t1 + 4 * u ? subPath(raw, t0, L - t1) : raw;
  if (k.layer === "over") return <>{pathLabel(k, false)}</>;
  const start = path[0];
  const startVisible = start && k.st.drawFrom === 0 && t0 === 0;
  return (
    <g>
      {startVisible ? <circle cx={start[0]} cy={start[1]} r={6 * u} fill={k.color} stroke="#000" strokeOpacity={0.3} strokeWidth={2 * u} /> : null}
      <StrokePath
        pts={path}
        color={k.color}
        width={4.5 * u}
        dash={[14 * u, 10 * u]}
        drawFrom={k.st.drawFrom}
        drawTo={k.st.drawTo}
        arrow={22 * u}
        casing={2.5 * u}
      casingColor={casingColor(k.color)}
      />
    </g>
  );
};

const Line: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  if (k.layer === "over") return <>{pathLabel(k, false)}</>;
  return (
    <StrokePath
      pts={k.pts}
      color={k.color}
      width={4.5 * u}
      dash={k.o.style.dash ? [16 * u, 11 * u] : undefined}
      drawFrom={k.st.drawFrom}
      drawTo={k.st.drawTo}
      casing={2.5 * u}
      casingColor={casingColor(k.color)}
    />
  );
};

const Polygon: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  if (k.pts.length < 3) return null;
  if (k.layer === "over") {
    return <>{areaLabel(k)}</>;
  }
  const closed = [...k.pts, k.pts[0]!];
  const shown = k.st.drawTo - k.st.drawFrom;
  return (
    <g>
      {k.o.style.fill ? <path d={pathD(k.pts, true)} fill={rgba(k.color, 0.16 * shown)} stroke="none" /> : null}
      <StrokePath
        pts={closed}
        color={k.color}
        width={4 * u}
        dash={k.o.style.dash ? [14 * u, 10 * u] : undefined}
        drawFrom={k.st.drawFrom}
        drawTo={k.st.drawTo}
        casing={2 * u}
        casingColor={casingColor(k.color)}
      />
    </g>
  );
};

const Zone: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  if (k.pts.length < 3) return null;
  const op = reveal(k.st);
  if (k.layer === "over") {
    return <g opacity={op}>{areaLabel(k)}</g>;
  }
  const d = pathD(k.pts, true);
  const hatch = `hatch-${k.o.id}`;
  const gap = 16 * u;
  return (
    <g opacity={op}>
      {k.o.style.fill ? (
        <>
          <defs>
            <pattern id={hatch} patternUnits="userSpaceOnUse" width={gap} height={gap} patternTransform="rotate(45)">
              <rect x={0} y={0} width={4 * u} height={gap} fill={k.color} fillOpacity={0.32} />
            </pattern>
          </defs>
          <path d={d} fill={rgba(mix(k.color, "#ffffff", 0.25), 0.13)} stroke="none" />
          <path d={d} fill={`url(#${hatch})`} stroke="none" />
        </>
      ) : null}
      <path
        d={d}
        fill="none"
        stroke={k.color}
        strokeOpacity={0.95}
        strokeWidth={3.5 * u}
        strokeLinejoin="round"
        strokeDasharray={k.o.style.dash ? `${14 * u} ${10 * u}` : undefined}
      />
    </g>
  );
};

const Ring: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  const op = reveal(k.st);
  if (k.layer === "under") return null;
  const base = Math.max(k.pj.tokenR * 1.6, 22 * u) * k.st.scale;
  const ph = pulsePhase(k.st.local, 36);
  const rMain = base * (1 + 0.035 * Math.sin(2 * Math.PI * ph));
  const rEcho = base * (1 + 0.6 * ph);
  const first = k.pts[0];
  return (
    <g opacity={op}>
      {k.pts.map((p, i) => (
        <g key={i}>
          {k.o.style.fill ? <circle cx={p[0]} cy={p[1]} r={rMain} fill={rgba(k.color, 0.18)} /> : null}
          <circle cx={p[0]} cy={p[1]} r={rEcho} fill="none" stroke={k.color} strokeWidth={3 * u * (1 - ph)} opacity={0.6 * (1 - ph)} />
          <circle cx={p[0]} cy={p[1]} r={rMain} fill="none" stroke="#000" strokeOpacity={0.3} strokeWidth={7 * u} />
          <circle
            cx={p[0]}
            cy={p[1]}
            r={rMain}
            fill="none"
            stroke={k.color}
            strokeWidth={4 * u}
            strokeDasharray={k.o.style.dash ? `${10 * u} ${7 * u}` : undefined}
            strokeDashoffset={k.o.style.dash ? -k.st.local * 1.2 * u : undefined}
          />
        </g>
      ))}
      {first ? labelPill(k.o.label, first[0], first[1] - base - 30 * u, k.color, k) : null}
    </g>
  );
};

const Spotlight: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  if (k.layer === "under") return null;
  const op = reveal(k.st);
  const R = Math.max(4.5 * k.pj.s, 70 * u) * Math.max(0.001, k.st.scale);
  const id = `spot-${k.o.id}`;
  const first = k.pts[0];
  return (
    <g>
      <defs>
        <radialGradient id={`${id}-hole`}>
          <stop offset="0%" stopColor="#000" />
          <stop offset="72%" stopColor="#000" />
          <stop offset="100%" stopColor="#fff" />
        </radialGradient>
        <mask id={`${id}-mask`} maskUnits="userSpaceOnUse" x={0} y={0} width={k.pj.width} height={k.pj.height}>
          <rect x={0} y={0} width={k.pj.width} height={k.pj.height} fill="#fff" />
          {k.pts.map((p, i) => (
            <circle key={i} cx={p[0]} cy={p[1]} r={R} fill={`url(#${id}-hole)`} />
          ))}
        </mask>
      </defs>
      <rect x={0} y={0} width={k.pj.width} height={k.pj.height} fill="#000" opacity={0.58 * op} mask={`url(#${id}-mask)`} />
      <g opacity={op}>
        {k.pts.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={R * 0.86} fill="none" stroke={k.color} strokeOpacity={0.55} strokeWidth={2.5 * u} />
        ))}
        {first ? labelPill(k.o.label, first[0], first[1] - R * 0.86 - 26 * u, k.color, k) : null}
      </g>
    </g>
  );
};

const Callout: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  if (k.layer === "under") return null;
  const a = k.pts[0];
  if (!a || !k.o.label) return null;
  const op = reveal(k.st);
  const fs = 34 * u;
  const padX = 16 * u;
  const padY = 9 * u;
  const text = k.o.label.toUpperCase();
  const w = estimateTextWidth(text, fs, "title", 0.05) + 2 * padX;
  const h = fs * 1.08 + 2 * padY;
  const gap = 34 * u;
  const [bx, by] = clampBox(a[0] - w / 2, a[1] - gap - h, w, h, k.pj.safe);
  const filled = k.o.style.fill;
  const bg = filled ? k.color : k.theme.panel;
  const fg = filled ? readableOn(k.color, k.theme.panel, "#ffffff") : k.color;
  const sc = k.st.scale;
  // pointer from the box edge nearest the anchor down/up to the anchor
  const px = Math.min(Math.max(a[0], bx + 10 * u), bx + w - 10 * u);
  const py = a[1] < by ? by : by + h;
  return (
    <g opacity={op} transform={`translate(${a[0]} ${a[1]}) scale(${sc}) translate(${-a[0]} ${-a[1]})`}>
      <line x1={px} y1={py} x2={a[0]} y2={a[1]} stroke="#000" strokeOpacity={0.35} strokeWidth={6 * u} strokeLinecap="round" />
      <line x1={px} y1={py} x2={a[0]} y2={a[1]} stroke={k.color} strokeWidth={3 * u} strokeLinecap="round" />
      <circle cx={a[0]} cy={a[1]} r={7 * u} fill={k.color} stroke={k.theme.panel} strokeWidth={2.5 * u} />
      <rect x={bx + 3 * u} y={by + 4 * u} width={w} height={h} rx={7 * u} fill="#000" opacity={0.3} />
      <rect
        x={bx}
        y={by}
        width={w}
        height={h}
        rx={7 * u}
        fill={bg}
        fillOpacity={filled ? 1 : 0.92}
        stroke={filled ? "none" : k.color}
        strokeWidth={filled ? 0 : 2.5 * u}
      />
      <rect x={bx} y={by} width={6 * u} height={h} rx={3 * u} fill={filled ? k.theme.accent : k.color} opacity={filled ? 0.95 : 0} />
      <text
        x={bx + w / 2 + (filled ? 3 * u : 0)}
        y={by + h / 2 + fs * 0.36}
        textAnchor="middle"
        fontFamily={TITLE_STACK}
        fontWeight={800}
        fontSize={fs}
        letterSpacing="0.05em"
        fill={fg}
      >
        {text}
      </text>
    </g>
  );
};

const Distance: React.FC<KindProps> = (k) => {
  const u = k.pj.u;
  const a = k.pts[0];
  const b = k.pts[1];
  if (!a || !b) return null;
  const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const nx = -Math.sin(ang) * 14 * u;
  const ny = Math.cos(ang) * 14 * u;
  if (k.layer === "over") {
    if (k.st.drawTo < 0.999) return null;
    return <>{labelPill(distanceText(k.world, k.o.label), (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, k.color, k, false)}</>;
  }
  const tick = (p: P2) => `M${p[0] - nx} ${p[1] - ny} L${p[0] + nx} ${p[1] + ny}`;
  return (
    <g>
      <StrokePath
        pts={[a, b]}
        color={k.color}
        width={3.5 * u}
        dash={k.o.style.dash ? [12 * u, 8 * u] : undefined}
        drawFrom={k.st.drawFrom}
        drawTo={k.st.drawTo}
        casing={2.5 * u}
      casingColor={casingColor(k.color)}
      />
      {k.st.drawFrom === 0 ? <path d={tick(a)} stroke={k.color} strokeWidth={3.5 * u} strokeLinecap="round" /> : null}
      {k.st.drawTo >= 0.999 ? <path d={tick(b)} stroke={k.color} strokeWidth={3.5 * u} strokeLinecap="round" /> : null}
    </g>
  );
};

const RENDERERS: Record<Overlay["kind"], React.FC<KindProps>> = {
  run_arrow: RunArrow,
  pass_line: PassLine,
  zone: Zone,
  line: Line,
  ring: Ring,
  spotlight: Spotlight,
  label: Callout,
  distance: Distance,
  polygon: Polygon,
};

/**
 * Draws every overlay visible at `frame` ([from, to)) for one layer. "under" = path-like overlays beneath the tokens;
 * "over" = rings, spotlights, callouts and all overlay labels above the tokens.
 */
export const Overlays: React.FC<{ props: RenderProps; frame: number; layer: Layer }> = ({ props, frame, layer }) => {
  const pj = useProjector();
  const glowId = `ov-glow-${layer}`;
  const items: React.ReactNode[] = [];
  // spotlights dim first, so every ring / label / callout of this layer stays on top of the dimming
  const ordered = [...props.overlays].sort((a, b) => Number(b.kind === "spotlight") - Number(a.kind === "spotlight"));
  for (const o of ordered) {
    const st = animState(o, frame);
    if (!st.visible || st.opacity <= 0) continue;
    const world = overlayPoints(o, frame);
    const pts = world.map(([x, y]) => pj.project(x, y));
    const R = RENDERERS[o.kind];
    const color = resolveColor(props.theme, o.style.color);
    const k: KindProps = { o, st, world, pts, color, theme: props.theme, pj, layer, glowId, props, frame };
    items.push(
      <g key={o.id} opacity={st.opacity}>
        <R {...k} />
      </g>,
    );
  }
  if (items.length === 0) return null;
  return (
    <svg width={pj.width} height={pj.height} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <filter id={glowId} filterUnits="userSpaceOnUse" x={0} y={0} width={pj.width} height={pj.height}>
          <feGaussianBlur stdDeviation={6 * pj.u} />
        </filter>
      </defs>
      {items}
    </svg>
  );
};
