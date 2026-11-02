// Headless render entry used by the Python engine (argv only; never via a shell).
// Usage: node scripts/render.mjs --composition <id> --out <file.mp4> [--props <props.json>]
//        [--scale 1] [--frames a-b] [--json-progress true|false] [--still <frame> (writes PNG)]
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i];
    if (!k?.startsWith("--")) throw new Error(`bad arg: ${k}`);
    out[k.slice(2)] = argv[i + 1];
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
if (!args.composition || !args.out) {
  console.error("required: --composition <id> --out <path>");
  process.exit(2);
}
const inputProps = args.props ? JSON.parse(readFileSync(resolve(args.props), "utf8")) : {};
const jsonProgress = (args["json-progress"] ?? "true") === "true";
const browserExecutable = process.env.TMS_BROWSER_EXECUTABLE || null;
// A regular Chrome only supports the new headless mode -> "chrome-for-testing".
const chromeMode = browserExecutable ? "chrome-for-testing" : "headless-shell";
const scale = args.scale ? Number(args.scale) : 1;

const serveUrl = await bundle({ entryPoint: join(root, "src", "index.ts"), publicDir: join(root, "public") });
const composition = await selectComposition({ serveUrl, id: args.composition, inputProps, browserExecutable, chromeMode });

if (args.still !== undefined) {
  await renderStill({
    serveUrl, composition, inputProps, output: resolve(args.out), frame: Number(args.still),
    imageFormat: "png", scale, browserExecutable, chromeMode,
  });
  console.log(JSON.stringify({ done: true, still: Number(args.still), out: resolve(args.out) }));
  process.exit(0);
}

let frameRange = null;
if (args.frames) {
  const [a, b] = args.frames.split("-").map(Number);
  frameRange = [a, b];
}
let last = -1;
await renderMedia({
  serveUrl, composition, inputProps, codec: "h264", pixelFormat: "yuv420p", outputLocation: resolve(args.out),
  imageFormat: "jpeg", jpegQuality: 92, scale, frameRange, muted: true, enforceAudioTrack: false, browserExecutable, chromeMode,
  colorSpace: "bt709",
  concurrency: Math.max(1, Math.floor((await import("node:os")).cpus().length / 2)),
  onProgress: ({ progress }) => {
    const pct = Math.floor(progress * 100);
    if (jsonProgress && pct !== last && pct % 5 === 0) {
      last = pct;
      console.log(JSON.stringify({ progress: pct }));
    }
  },
});
console.log(JSON.stringify({ done: true, out: resolve(args.out), frames: composition.durationInFrames }));
