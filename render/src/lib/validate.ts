// Runtime validation of render_props against the JSON Schema contract (ajv, Draft 2020-12), plus the cheap
// cross-field checks the renderer relies on (one track sample per frame). Used by calculateMetadata.
import Ajv2020 from "ajv/dist/2020";
import type { ErrorObject, ValidateFunction } from "ajv";
import schema from "../../../schemas/artifacts/render_props.schema.json";
import type { RenderProps } from "../generated/render_props";

let compiled: ValidateFunction | null = null;

function validator(): ValidateFunction {
  if (compiled === null) {
    const ajv = new Ajv2020({ allErrors: true, strict: true, allowUnionTypes: true });
    compiled = ajv.compile(schema);
  }
  return compiled;
}

function describe(e: ErrorObject): string {
  const at = e.instancePath === "" ? "(root)" : e.instancePath;
  const p = e.params as Record<string, unknown>;
  let extra = "";
  if (e.keyword === "additionalProperties") extra = `: '${String(p.additionalProperty)}'`;
  else if (e.keyword === "enum") extra = `: ${JSON.stringify(p.allowedValues)}`;
  else if (e.keyword === "const") extra = `: ${JSON.stringify(p.allowedValue)}`;
  return `${at} ${e.message ?? e.keyword}${extra}`;
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
}

/** Schema validation only. */
export function validateSchema(props: unknown): ValidationResult {
  const v = validator();
  const ok = v(props) as boolean;
  if (ok) return { ok: true, errors: [] };
  const seen = new Set<string>();
  const errors: string[] = [];
  for (const e of v.errors ?? []) {
    // oneOf/anyOf produce one line per failing branch; keep the first occurrence of each message
    const line = describe(e);
    if (!seen.has(line)) {
      seen.add(line);
      errors.push(line);
    }
  }
  return { ok: false, errors };
}

/** Cross-field checks the schema cannot express: every per-frame array has exactly one sample per frame. */
export function checkConsistency(p: RenderProps): string[] {
  const n = p.durationInFrames;
  const errs: string[] = [];
  if (p.camera.length !== 3 * n) errs.push(`/camera has ${p.camera.length} values, expected 3 x durationInFrames = ${3 * n}`);
  if (p.tracks.ball.length !== 0 && p.tracks.ball.length !== 3 * n)
    errs.push(`/tracks/ball has ${p.tracks.ball.length} values, expected ${3 * n}`);
  for (const [id, t] of Object.entries(p.tracks.players)) {
    if (t.length !== 2 * n) errs.push(`/tracks/players/${id} has ${t.length} values, expected ${2 * n}`);
  }
  for (const e of p.entities) {
    if (!(e.id in p.tracks.players)) errs.push(`/entities ${e.id} has no track in /tracks/players`);
  }
  const portrait = p.orientation === "portrait";
  const square = p.orientation === "square";
  if (portrait && !(p.height > p.width)) errs.push(`orientation portrait needs height > width (got ${p.width}x${p.height})`);
  if (square && p.width !== p.height) errs.push(`orientation square needs width == height (got ${p.width}x${p.height})`);
  if (!portrait && !square && !(p.width > p.height))
    errs.push(`orientation landscape needs width > height (got ${p.width}x${p.height})`);
  for (let i = 2; i < p.camera.length; i += 3) {
    if (!((p.camera[i] ?? 0) > 0)) {
      errs.push(`/camera frame ${(i - 2) / 3} has non-positive width ${p.camera[i]}`);
      break;
    }
  }
  return errs;
}

export class RenderPropsError extends Error {
  constructor(public readonly issues: string[]) {
    const shown = issues.slice(0, 12);
    const more = issues.length > shown.length ? `\n  ... and ${issues.length - shown.length} more` : "";
    super(`Invalid render_props (${issues.length} problem${issues.length === 1 ? "" : "s"}):\n  ${shown.join("\n  ")}${more}`);
    this.name = "RenderPropsError";
  }
}

/** Throws a readable RenderPropsError unless `props` is schema-valid and internally consistent. */
export function assertRenderProps(props: unknown): RenderProps {
  const r = validateSchema(props);
  if (!r.ok) throw new RenderPropsError(r.errors);
  const p = props as RenderProps;
  const c = checkConsistency(p);
  if (c.length > 0) throw new RenderPropsError(c);
  return p;
}
