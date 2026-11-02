// Copies tests/fixtures/artifacts/render_props.json to src/fixtures/render_props.fixture.json (the TacticVideo
// defaultProps). A vitest asserts both parse to the same JSON, so re-run this whenever the test fixture changes.
import { copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "..", "tests", "fixtures", "artifacts", "render_props.json");
const dst = join(root, "src", "fixtures", "render_props.fixture.json");
copyFileSync(src, dst);
console.log(`sync:fixture: ${src} -> ${dst}`);
