import React from "react";
import type { RenderProps } from "../generated/render_props";
import { TITLE_STACK } from "../fonts";
import { clamp01 } from "../lib/anim";
import { rgba } from "../lib/colors";
import { PAUSE_BADGE_FONT_1080 } from "../lib/hud";
import { safeArea, unit } from "../lib/layout";
import { cameraAt, spanAt } from "../lib/tracks";

/** Subtle "paused" treatment inside freeze spans: edge vignette + small pause badge (top-right of the safe area). */
export const FreezeVignette: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const span = spanAt(props.freeze, frame);
  if (!span) return null;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const k = Math.min(clamp01((frame - span[0] + 1) / 5), clamp01((span[1] - frame) / 5));
  const fs = PAUSE_BADGE_FONT_1080 * u;
  return (
    <div style={{ position: "absolute", inset: 0, opacity: k }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.42) 100%)",
          boxShadow: `inset 0 0 0 ${4 * u}px ${rgba(theme.ink, 0.12)}`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: safe.y0,
          right: width - safe.x1,
          display: "flex",
          alignItems: "center",
          gap: 10 * u,
          padding: `${8 * u}px ${16 * u}px`,
          background: rgba(theme.panel, 0.82),
          borderRadius: 999,
          border: `${1.5 * u}px solid ${rgba(theme.ink, 0.18)}`,
        }}
      >
        <div style={{ display: "flex", gap: 5 * u }}>
          <div style={{ width: 6 * u, height: fs * 0.8, background: theme.ink, borderRadius: 2 * u }} />
          <div style={{ width: 6 * u, height: fs * 0.8, background: theme.ink, borderRadius: 2 * u }} />
        </div>
        <div style={{ fontFamily: TITLE_STACK, fontWeight: 600, fontSize: fs, letterSpacing: "0.16em", color: theme.ink, lineHeight: 1 }}>
          PAUSED
        </div>
      </div>
    </div>
  );
};

/** debug.overlay: frame / camera readout and the 90% safe-area guide. */
export const DebugOverlay: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  if (!props.debug.overlay) return null;
  const { width, height } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const cam = cameraAt(props, frame);
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div
        style={{
          position: "absolute",
          left: safe.x0,
          top: safe.y0,
          width: safe.x1 - safe.x0,
          height: safe.y1 - safe.y0,
          outline: `${2 * u}px dashed rgba(255,0,255,0.7)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 12 * u,
          top: 12 * u,
          fontFamily: "monospace",
          fontSize: 20 * u,
          color: "#ff66ff",
          background: "rgba(0,0,0,0.6)",
          padding: 6 * u,
        }}
      >
        {`f${frame}  cam ${cam.cx.toFixed(2)},${cam.cy.toFixed(2)} w${cam.w.toFixed(2)}  ${width}x${height} ${props.orientation}`}
      </div>
    </div>
  );
};
