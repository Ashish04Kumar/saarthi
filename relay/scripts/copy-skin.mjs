// Copy the bundled Saarthi skin next to the page and write skin/manifest.json (frame lists per state),
// so the browser shows exactly the same character as the desktop.
import { cpSync, rmSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, "..", "..", "src", "saarthi", "skins", "saarthi");
const to = join(here, "..", "public", "skin");
rmSync(to, { recursive: true, force: true });
cpSync(from, to, { recursive: true });

const meta = JSON.parse(readFileSync(join(from, "skin.json"), "utf8"));
const out = {};
for (const [key, spec] of Object.entries(meta.states)) {
  const dir = spec.frames.split("/")[0];
  const files = readdirSync(join(from, dir)).filter((f) => f.endsWith(".png")).sort();
  out[key] = { frames: files.map((f) => `${dir}/${f}`), fps: spec.fps ?? meta.fps ?? 10, loop: spec.loop !== false };
}
writeFileSync(join(to, "manifest.json"), JSON.stringify(out));
console.log(`skin copied to public/skin (${Object.keys(out).length} animations)`);
