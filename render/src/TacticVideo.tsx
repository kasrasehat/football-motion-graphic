import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Ball } from "./components/Ball";
import { CameraRig } from "./components/CameraRig";
import { Captions } from "./components/Captions";
import { EndCardView, TitleCardView } from "./components/Cards";
import { Graphics } from "./components/graphics/registry";
import { DebugOverlay, FreezeVignette } from "./components/Hud";
import { Overlays } from "./components/overlays/Overlays";
import { Pitch } from "./components/Pitch";
import { PlayerLabels, Players } from "./components/Players";
import { PrincipleRailPanel } from "./components/PrincipleRail";
import { SceneTitle } from "./components/SceneTitle";
import { loadFonts } from "./fonts";
import type { RenderProps } from "./generated/render_props";
import { clamp01 } from "./lib/anim";
import { mix } from "./lib/colors";
import { spanAt } from "./lib/tracks";
import type { TacticVideoProps } from "./TacticVideo.meta";

loadFonts();

const PITCH_FADE = 6;

/** Opacity of the world layer: 1 inside a pitchVisible span, short fades at span edges (not at video start/end). */
function pitchOpacity(p: RenderProps, frame: number): number {
  const s = spanAt(p.pitchVisible, frame);
  if (!s) return 0;
  const fin = s[0] <= 0 ? 1 : clamp01((frame - s[0] + 1) / PITCH_FADE);
  const fout = s[1] >= p.durationInFrames ? 1 : clamp01((s[1] - frame) / PITCH_FADE);
  return Math.min(fin, fout);
}

/** The whole video: a pure function of (frame, render_props). */
export const TacticVideo: React.FC<TacticVideoProps> = (props) => {
  const frame = useCurrentFrame();
  const p = props as RenderProps;
  const worldOpacity = pitchOpacity(p, frame);
  const bg = mix(p.theme.panel, "#000000", 0.2);
  return (
    <AbsoluteFill style={{ backgroundColor: bg, overflow: "hidden" }}>
      {worldOpacity > 0 ? (
        <AbsoluteFill style={{ opacity: worldOpacity }}>
          <CameraRig props={p}>
            <Pitch theme={p.theme} />
            <Overlays props={p} frame={frame} layer="under" />
            <Players props={p} frame={frame} />
            <Ball props={p} frame={frame} />
            <Overlays props={p} frame={frame} layer="over" />
            <PlayerLabels props={p} frame={frame} />
          </CameraRig>
        </AbsoluteFill>
      ) : null}
      <PrincipleRailPanel props={p} />
      <Graphics props={p} frame={frame} />
      <FreezeVignette props={p} frame={frame} />
      <SceneTitle props={p} frame={frame} />
      <TitleCardView props={p} frame={frame} />
      <EndCardView props={p} frame={frame} />
      <Captions props={p} frame={frame} />
      <DebugOverlay props={p} frame={frame} />
    </AbsoluteFill>
  );
};
