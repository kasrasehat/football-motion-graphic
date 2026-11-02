import React from "react";
import type { RenderProps } from "../generated/render_props";
import { TITLE_STACK } from "../fonts";
import { clamp01, easeInOutCubic, easeOutCubic } from "../lib/anim";
import { rgba } from "../lib/colors";
import { sceneTitleLayout } from "../lib/hud";
import { safeArea, unit } from "../lib/layout";

/** Scene title lower-third (bottom-left of the safe area; lifted above any bottom caption it would collide with). */
export const SceneTitle: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const lay = sceneTitleLayout(props, frame);
  if (!lay) return null;
  const { scene, bottom, fontSize: fs } = lay;
  const [a, b] = lay.window;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const inP = easeOutCubic((frame - a + 1) / 10);
  const outP = easeInOutCubic((b - frame) / 8);
  const wipe = Math.min(inP, outP);
  const title = scene.title.toUpperCase();
  const num = String(lay.index + 1).padStart(2, "0");
  return (
    <div
      style={{
        position: "absolute",
        left: safe.x0,
        bottom,
        display: "flex",
        alignItems: "stretch",
        clipPath: `inset(-20% ${(100 * (1 - wipe)).toFixed(3)}% -20% 0)`,
        opacity: clamp01(wipe * 3),
        filter: `drop-shadow(0 ${5 * u}px ${14 * u}px rgba(0,0,0,0.4))`,
      }}
    >
      <div style={{ width: 9 * u, background: theme.accent, borderRadius: `${3 * u}px 0 0 ${3 * u}px` }} />
      <div
        style={{
          background: rgba(theme.panel, 0.93),
          padding: `${12 * u}px ${24 * u}px ${12 * u}px ${18 * u}px`,
          display: "flex",
          alignItems: "baseline",
          gap: 16 * u,
          borderRadius: `0 ${4 * u}px ${4 * u}px 0`,
        }}
      >
        <span
          style={{
            fontFamily: TITLE_STACK,
            fontWeight: 600,
            fontSize: fs * 0.62,
            letterSpacing: "0.08em",
            color: theme.accent,
          }}
        >
          {num}
        </span>
        <span
          style={{
            fontFamily: TITLE_STACK,
            fontWeight: 800,
            fontSize: fs,
            letterSpacing: "0.03em",
            lineHeight: 1.05,
            color: theme.ink,
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </span>
      </div>
    </div>
  );
};
