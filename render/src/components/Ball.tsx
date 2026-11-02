import React from "react";
import type { RenderProps } from "../generated/render_props";
import { ballAt } from "../lib/tracks";
import { useProjector } from "./CameraRig";

const BALL_DIAMETER_M = 0.7; // exaggerated (real ball is 0.22 m) so it reads at full-pitch zoom
const BALL_MIN_R_1080 = 8;

/**
 * White ball with a seam hint, drawn at its ground point. Height z (cm in props) only moves/softens the shadow and
 * slightly enlarges the ball, so the ball centre always sits where tms.render.projection.project_ball says.
 */
export const Ball: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const pj = useProjector();
  const b = ballAt(props, frame);
  if (!b) return null;
  const [x, y, z] = b;
  const [sx, sy] = pj.project(x, y);
  const zc = Math.max(0, z);
  const r = Math.max((BALL_DIAMETER_M / 2) * pj.s, BALL_MIN_R_1080 * pj.u) * (1 + Math.min(zc, 12) * 0.035);
  // shadow falls down-right of the ball and drifts further / fades / blurs as the ball rises
  const off = (0.12 + zc * 0.3) * pj.s;
  const shadowScale = 1 + Math.min(zc, 12) * 0.05;
  const shadowOpacity = 0.45 / (1 + zc * 0.25);
  const id = `ball-${pj.width}x${pj.height}`;
  return (
    <svg width={pj.width} height={pj.height} style={{ position: "absolute", left: 0, top: 0 }}>
      <defs>
        <radialGradient id={`${id}-shade`} cx="38%" cy="34%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="62%" stopColor="#f4f6f8" />
          <stop offset="100%" stopColor="#c9d0d6" />
        </radialGradient>
        <filter id={`${id}-blur`} x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation={Math.max(0.8, r * (0.25 + zc * 0.05))} />
        </filter>
      </defs>
      <ellipse
        cx={sx + off * 0.7}
        cy={sy + off}
        rx={r * shadowScale}
        ry={r * shadowScale * 0.82}
        fill="#000000"
        opacity={shadowOpacity}
        filter={`url(#${id}-blur)`}
      />
      <circle cx={sx} cy={sy} r={r} fill={`url(#${id}-shade)`} stroke="#1a1f24" strokeOpacity={0.55} strokeWidth={Math.max(1, r * 0.1)} />
      <path
        d={`M${sx - r * 0.78} ${sy - r * 0.32} Q${sx - r * 0.35} ${sy - r * 0.95} ${sx + r * 0.3} ${sy - r * 0.8}`}
        fill="none"
        stroke="#3d454d"
        strokeOpacity={0.75}
        strokeWidth={Math.max(0.8, r * 0.11)}
        strokeLinecap="round"
      />
      <path
        d={`M${sx + r * 0.5} ${sy + r * 0.62} Q${sx + r * 0.85} ${sy + r * 0.2} ${sx + r * 0.78} ${sy - r * 0.18}`}
        fill="none"
        stroke="#3d454d"
        strokeOpacity={0.6}
        strokeWidth={Math.max(0.8, r * 0.1)}
        strokeLinecap="round"
      />
    </svg>
  );
};
