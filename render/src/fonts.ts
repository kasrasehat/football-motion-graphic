// Local OFL fonts (copied into public/fonts by `npm run fonts`); never fetched from the network at render time.
// loadFont() blocks rendering (delayRender) until each face is ready, so the first frame already uses them.
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import { FONT_BODY, FONT_TITLE } from "./lib/layout";

const FACES: { family: string; file: string; weight: string }[] = [
  { family: FONT_TITLE, file: "fonts/BarlowCondensed-SemiBold.woff2", weight: "600" },
  { family: FONT_TITLE, file: "fonts/BarlowCondensed-ExtraBold.woff2", weight: "800" },
  { family: FONT_BODY, file: "fonts/Inter-Medium.woff2", weight: "500" },
  { family: FONT_BODY, file: "fonts/Inter-Bold.woff2", weight: "700" },
];

let started = false;

/** Idempotent; called once at module load of the TacticVideo composition. */
export function loadFonts(): void {
  if (started) return;
  started = true;
  for (const f of FACES) {
    void loadFont({ family: f.family, url: staticFile(f.file), weight: f.weight, style: "normal", display: "block" });
  }
}

export const TITLE_STACK = `"${FONT_TITLE}", "Arial Narrow", sans-serif`;
export const BODY_STACK = `"${FONT_BODY}", "Segoe UI", Arial, sans-serif`;
