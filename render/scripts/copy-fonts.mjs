// Copies the OFL font files we use from @fontsource into public/fonts so renders never hit the network.
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const out = join(root, "public", "fonts");
mkdirSync(out, { recursive: true });

const FONTS = [
  ["@fontsource/barlow-condensed", "barlow-condensed-latin-600-normal.woff2", "BarlowCondensed-SemiBold.woff2"],
  ["@fontsource/barlow-condensed", "barlow-condensed-latin-800-normal.woff2", "BarlowCondensed-ExtraBold.woff2"],
  ["@fontsource/inter", "inter-latin-500-normal.woff2", "Inter-Medium.woff2"],
  ["@fontsource/inter", "inter-latin-700-normal.woff2", "Inter-Bold.woff2"],
];

let missing = 0;
for (const [pkg, file, target] of FONTS) {
  const src = join(root, "node_modules", pkg, "files", file);
  if (!existsSync(src)) {
    console.error(`font source missing: ${pkg}/files/${file}`);
    missing++;
    continue;
  }
  copyFileSync(src, join(out, target));
}
console.log(`fonts: ${FONTS.length - missing}/${FONTS.length} copied to public/fonts`);
process.exit(missing ? 1 : 0);
