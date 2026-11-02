import React, { createContext, useContext, useMemo } from "react";
import { useCurrentFrame } from "remotion";
import type { RenderProps } from "../generated/render_props";
import { safeArea, unit, type Rect } from "../lib/layout";
import {
  pxPerMetre,
  screenAngle,
  tokenRadiusPx,
  worldMatrix,
  worldToScreen,
  type Camera,
  type Orientation,
} from "../lib/projection";
import { cameraAt } from "../lib/tracks";

/** Everything a world-space component needs to place itself on screen for the current frame. */
export interface Projector {
  cam: Camera;
  width: number;
  height: number;
  orientation: Orientation;
  /** px per metre */
  s: number;
  /** size factor vs 1080p for screen-constant sizes */
  u: number;
  tokenR: number;
  safe: Rect;
  /** SVG transform mapping world metres to screen px */
  matrix: string;
  project: (x: number, y: number) => [number, number];
  /** screen angle (radians) of a world direction */
  angle: (dx: number, dy: number) => number;
}

const Ctx = createContext<Projector | null>(null);

export function makeProjector(cam: Camera, width: number, height: number, orientation: Orientation): Projector {
  const m = worldMatrix(cam, width, height, orientation);
  return {
    cam,
    width,
    height,
    orientation,
    s: pxPerMetre(cam.w, width, height, orientation),
    u: unit(width, height),
    tokenR: tokenRadiusPx(cam.w, width, height, orientation),
    safe: safeArea(width, height),
    matrix: `matrix(${m.join(" ")})`,
    project: (x, y) => worldToScreen(x, y, cam, width, height, orientation),
    angle: (dx, dy) => screenAngle(dx, dy, orientation),
  };
}

/** Applies the per-frame camera (props.camera) to every world-space child via context. */
export const CameraRig: React.FC<{ props: RenderProps; children: React.ReactNode }> = ({ props, children }) => {
  const frame = useCurrentFrame();
  const cam = cameraAt(props, frame);
  const proj = useMemo(
    () => makeProjector(cam, props.width, props.height, props.orientation),
    [cam.cx, cam.cy, cam.w, props.width, props.height, props.orientation],
  );
  return <Ctx.Provider value={proj}>{children}</Ctx.Provider>;
};

export function useProjector(): Projector {
  const p = useContext(Ctx);
  if (p === null) throw new Error("useProjector() must be used inside <CameraRig>");
  return p;
}
