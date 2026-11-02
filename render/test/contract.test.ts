import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { tacticVideoDefaultProps } from "../src/TacticVideo.meta";
import { fixture, RENDER_DIR } from "./helpers";

describe("contract artefacts", () => {
  it("defaultProps fixture copy is identical to tests/fixtures/artifacts/render_props.json", () => {
    const copy = JSON.parse(readFileSync(join(RENDER_DIR, "src", "fixtures", "render_props.fixture.json"), "utf8"));
    expect(copy).toStrictEqual(fixture());
    expect(JSON.parse(JSON.stringify(tacticVideoDefaultProps))).toStrictEqual(fixture());
  });

  it("generated types are up to date with the schema (npm run gen:types)", () => {
    const out = execFileSync(process.execPath, [join(RENDER_DIR, "scripts", "gen-types.mjs"), "--check"], {
      cwd: RENDER_DIR,
      encoding: "utf8",
    });
    expect(out).toContain("up to date");
  });
});
