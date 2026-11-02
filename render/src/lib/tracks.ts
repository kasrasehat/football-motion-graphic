// Frame-indexed lookups into render_props. No interpolation, no motion maths: the engine already emitted one
// sample per frame. Frames outside the track are clamped to the nearest sample.
import type { RenderProps, Span } from "../generated/render_props";
import type { Camera } from "./projection";

function clampIndex(frame: number, n: number): number {
  if (n <= 0) return 0;
  return Math.max(0, Math.min(Math.floor(frame), n - 1));
}

/** Camera (cx, cy, w) in metres at `frame`. */
export function cameraAt(props: Pick<RenderProps, "camera">, frame: number): Camera {
  const c = props.camera;
  const i = clampIndex(frame, Math.floor(c.length / 3)) * 3;
  return { cx: (c[i] ?? 5250) / 100, cy: (c[i + 1] ?? 3400) / 100, w: (c[i + 2] ?? 10500) / 100 };
}

/** Player position in metres at `frame`, or null when the entity has no track. */
export function playerAt(props: Pick<RenderProps, "tracks">, id: string, frame: number): [number, number] | null {
  const t = props.tracks.players[id];
  if (!t || t.length < 2) return null;
  const i = clampIndex(frame, Math.floor(t.length / 2)) * 2;
  return [(t[i] ?? 0) / 100, (t[i + 1] ?? 0) / 100];
}

/** Ball (x, y, z) in metres at `frame`, or null when there is no ball track. */
export function ballAt(props: Pick<RenderProps, "tracks">, frame: number): [number, number, number] | null {
  const b = props.tracks.ball;
  if (b.length < 3) return null;
  const i = clampIndex(frame, Math.floor(b.length / 3)) * 3;
  return [(b[i] ?? 0) / 100, (b[i + 1] ?? 0) / 100, (b[i + 2] ?? 0) / 100];
}

/** Half-open span test: from <= frame < to. */
export function inSpan(span: Span, frame: number): boolean {
  return frame >= span[0] && frame < span[1];
}

export function spanAt(spans: Span[], frame: number): Span | null {
  for (const s of spans) if (inSpan(s, frame)) return s;
  return null;
}
