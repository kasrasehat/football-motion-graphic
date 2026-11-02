// Composition metadata for TacticVideo: props type, default props (the 90-frame fixture) and calculateMetadata.
// Kept free of React / fonts so it can be unit-tested in node.
import type { CalculateMetadataFunction } from "remotion";
import fixture from "./fixtures/render_props.fixture.json";
import type { RenderProps } from "./generated/render_props";
import { assertRenderProps } from "./lib/validate";

/** Remotion needs an index-signature props type; RenderProps is the generated contract type. */
export type TacticVideoProps = RenderProps & Record<string, unknown>;

export const tacticVideoDefaultProps = fixture as unknown as TacticVideoProps;

/** Validates props (ajv + consistency; throws a readable RenderPropsError) and derives the composition metadata. */
export const calculateTacticMetadata: CalculateMetadataFunction<TacticVideoProps> = ({ props }) => {
  const p = assertRenderProps(props);
  return { durationInFrames: p.durationInFrames, fps: p.fps, width: p.width, height: p.height };
};
