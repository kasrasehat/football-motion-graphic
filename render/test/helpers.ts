import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { RenderProps } from "../src/generated/render_props";

export const RENDER_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
export const REPO_DIR = join(RENDER_DIR, "..");

export function readJson<T = unknown>(...parts: string[]): T {
  return JSON.parse(readFileSync(join(REPO_DIR, ...parts), "utf8")) as T;
}

/** A fresh deep copy of the 90-frame render_props test fixture. */
export function fixture(): RenderProps {
  return readJson<RenderProps>("tests", "fixtures", "artifacts", "render_props.json");
}
