// Zero-dependency local unit test for webapp/index.html's esc() (F1 XSS).
// Not wired into CI (CI ships Python only); run locally with:
//   node scripts/webapp_esc.test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(root, "webapp", "index.html"), "utf8");

// Slice ESC_MAP and esc() by markers (avoids brace-matching the table literal),
// then evaluate both in one scope: esc() closes over ESC_MAP.
const escStart = html.indexOf("function esc(v) {");
const escEnd = html.indexOf("\n}", escStart);
const escSrc = html.slice(escStart, escEnd + 2);
const mapStart = html.indexOf("const ESC_MAP = {");
const mapEnd = html.indexOf("\n};", mapStart);
const mapSrc = html.slice(mapStart, mapEnd + 3);
if (escStart < 0 || mapStart < 0) {
  console.error("FAIL: ESC_MAP + esc() not found in webapp/index.html");
  process.exit(1);
}
const esc = eval(`(function(){ ${mapSrc}; ${escSrc}; return esc; })()`);

const cases = [
  ['<img src=x onerror=alert(1)>', "&lt;img"],
  ["<script>alert(1)</script>", "&lt;script"],
  ['"quoted"', "&quot;"],
  ["'single'", "&#39;"],
  ["`template ${7*7}`", "&#96;"],
  ["dollar$ign", "&#36;"],
  ["&lt;entity&gt;", "&amp;lt;"],
];

let fail = 0;
for (const [input, expect] of cases) {
  const out = esc(input);
  if (!out.includes(expect)) {
    console.error(`FAIL: esc(${JSON.stringify(input)}) = ${JSON.stringify(out)}; expected ${expect}`);
    fail++;
  }
  // Raw tag delimiters must never survive (plain-text attribute names like
  // "onerror=" are inert once brackets/quotes are escaped; do not flag them).
  if (/<img|<script|javascript:/i.test(out) || /[<>]/.test(out)) {
    console.error(`FAIL: raw injection survived: ${out}`);
    fail++;
  }
}

if (fail) {
  console.error(`${fail} esc() test(s) failed`);
  process.exit(1);
}
console.log("esc() local tests passed");
