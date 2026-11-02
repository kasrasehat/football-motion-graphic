import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

/** Toolchain smoke test used by `tms doctor`: 60 frames, 320x180. */
export const Smoke: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ backgroundColor: "#1f7a3a", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 40, height: 40, borderRadius: 20, background: "#ffffff", transform: `translateX(${frame * 3 - 90}px)` }} />
    </AbsoluteFill>
  );
};
