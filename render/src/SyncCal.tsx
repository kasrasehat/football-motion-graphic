import React from "react";
import { AbsoluteFill, CalculateMetadataFunction, useCurrentFrame } from "remotion";

/** A/V sync calibration (`tms qa sync-test`): black video with full-white frames at `flashes`. */
export type SyncCalProps = { durationInFrames: number; flashes: number[] };

export const syncCalDefaultProps: SyncCalProps = { durationInFrames: 180, flashes: [30, 75, 121, 150] };

export const calculateSyncCalMetadata: CalculateMetadataFunction<SyncCalProps> = ({ props }) => ({
  durationInFrames: props.durationInFrames,
  fps: 30,
  width: 320,
  height: 180,
});

export const SyncCal: React.FC<SyncCalProps> = ({ flashes }) => {
  const frame = useCurrentFrame();
  const on = flashes.includes(frame);
  return <AbsoluteFill style={{ backgroundColor: on ? "#ffffff" : "#000000" }} />;
};
