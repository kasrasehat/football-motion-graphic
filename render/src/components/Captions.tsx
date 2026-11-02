import React from "react";
import type { RenderProps } from "../generated/render_props";
import { BODY_STACK } from "../fonts";
import { clamp01 } from "../lib/anim";
import { CAPTION_PAD_X_1080, activeCaption, captionFontSize, captionLines } from "../lib/captions";
import { readableOn, rgba } from "../lib/colors";
import { CAPTION_LINE_HEIGHT, CAPTION_PAD_Y_1080 } from "../lib/hud";
import { safeArea, unit } from "../lib/layout";

/** Burned-in captions: <= 2 lines, active word highlighted, inside the 90% safe area, never clipped. */
export const Captions: React.FC<{ props: RenderProps; frame: number }> = ({ props, frame }) => {
  const c = activeCaption(props.captions, frame);
  if (!c) return null;
  const { width, height, theme } = props;
  const u = unit(width, height);
  const safe = safeArea(width, height);
  const fs = captionFontSize(c.lines, width, height);
  const lines = captionLines(c, frame);
  const fadeIn = clamp01((frame - c.from + 1) / 4);
  const fadeOut = clamp01((c.to - frame) / 4);
  const opacity = Math.min(fadeIn, fadeOut);
  const activeFg = readableOn(theme.accent, theme.panel, "#ffffff");
  const pos: React.CSSProperties =
    c.place === "top" ? { top: safe.y0 } : { bottom: height - safe.y1 };
  return (
    <div
      style={{
        position: "absolute",
        left: safe.x0,
        width: safe.x1 - safe.x0,
        display: "flex",
        justifyContent: "center",
        opacity,
        ...pos,
      }}
    >
      <div
        style={{
          background: rgba(theme.panel, 0.84),
          borderRadius: 14 * u,
          padding: `${CAPTION_PAD_Y_1080 * u}px ${CAPTION_PAD_X_1080 * u}px`,
          boxShadow: `0 ${6 * u}px ${24 * u}px rgba(0,0,0,0.35)`,
          border: `${1.5 * u}px solid ${rgba(theme.ink, 0.1)}`,
          maxWidth: safe.x1 - safe.x0,
          boxSizing: "border-box",
        }}
      >
        {lines.map((line, li) => (
          <div
            key={li}
            style={{
              fontFamily: BODY_STACK,
              fontWeight: 500,
              fontSize: fs,
              lineHeight: CAPTION_LINE_HEIGHT,
              whiteSpace: "nowrap",
              textAlign: "center",
              color: theme.ink,
              letterSpacing: "-0.005em",
            }}
          >
            {line.map((w, wi) => {
              const active = w.state === "active";
              return (
                <React.Fragment key={wi}>
                  {wi > 0 ? " " : null}
                  <span
                    style={{
                      padding: `0 ${0.14 * fs}px`,
                      margin: `0 ${-0.1 * fs}px`,
                      borderRadius: 6 * u,
                      background: active ? theme.accent : "transparent",
                      color: active ? activeFg : w.state === "future" ? rgba(theme.ink, 0.62) : theme.ink,
                    }}
                  >
                    {w.text}
                  </span>
                </React.Fragment>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};
