import React from "react";
import { Composition } from "remotion";
import { Smoke } from "./Smoke";
import { SyncCal, calculateSyncCalMetadata, syncCalDefaultProps } from "./SyncCal";
import { TacticVideo } from "./TacticVideo";
import { calculateTacticMetadata, tacticVideoDefaultProps } from "./TacticVideo.meta";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Smoke" component={Smoke} durationInFrames={60} fps={30} width={320} height={180} />
    <Composition
      id="SyncCal"
      component={SyncCal}
      defaultProps={syncCalDefaultProps}
      calculateMetadata={calculateSyncCalMetadata}
      durationInFrames={syncCalDefaultProps.durationInFrames}
      fps={30}
      width={320}
      height={180}
    />
    <Composition
      id="TacticVideo"
      component={TacticVideo}
      defaultProps={tacticVideoDefaultProps}
      calculateMetadata={calculateTacticMetadata}
      durationInFrames={tacticVideoDefaultProps.durationInFrames}
      fps={30}
      width={tacticVideoDefaultProps.width}
      height={tacticVideoDefaultProps.height}
    />
  </>
);
