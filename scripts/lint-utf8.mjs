#!/usr/bin/env node
// UTF-8 mojibake guard for apps/desktop.
// Catches the classic "UTF-8 bytes decoded as Latin-1 and re-encoded as UTF-8"
// mistake that produced "â†'", "â€¦", "â€"", "Â·" in CoachPanel.tsx,
// GameDetailPage.tsx, and ProfileDashboard.tsx (BBF-4 / BBF-5 sprints).
//
// Run via: pnpm lint:utf8   (or: node ./scripts/lint-utf8.mjs)
// Wired into: pnpm lint:ci    (prepended before tsgo --noEmit)

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const PROJECT_ROOT = process.cwd();
const SCAN_DIRS = ["src", "scripts", "i18next.config.ts", "index.html"];
const SKIP_DIRS = new Set([
  "node_modules", "dist", "src-tauri", ".git", ".archive",
  ".github", ".vscode", ".husky",
]);
const SKIP_FILES = new Set([
  "src/bindings/generated.ts",
  "src/routeTree.gen.ts",
  "scripts/lint-utf8.mjs",
]);
const SKIP_SUFFIXES = [".bak", ".bak."];  // matches *.bak, *.bak.<ts>

// Moibake byte sequences (UTF-8) → real Unicode char.
// Listed in the order discovered in BBF-4/BBF-5 + the four common Latin-script
// mojibake that any real codebase eventually produces.
const MOJIBAKE = [
  { needle: "â†'", hint: "→ (U+2192)" },
  { needle: "â†‘", hint: "↑ (U+2191)" },
  { needle: "â†\"", hint: "↓ (U+2193)" },
  { needle: "â€\"", hint: "— (U+2014)" },
  { needle: "â€¦", hint: "… (U+2026)" },
  { needle: "Â·",  hint: "· (U+00B7)" },
  { needle: "Ã©", hint: "é (U+00E9)" },
  { needle: "Ã¨", hint: "è (U+00E8)" },
  { needle: "Ã ", hint: "à (U+00E0)" },
  { needle: "Â ", hint: "NBSP (U+00A0)" },
];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) yield* walk(full);
    else yield full;
  }
}

function shouldScan(rel) {
  if (SKIP_FILES.has(rel)) return false;
  if (SKIP_SUFFIXES.some((s) => rel.includes(s))) return false;
  return /\.(ts|tsx|js|jsx|mjs|cjs|json|md|html|css|scss)$/.test(rel);
}

const hits = [];
for (const target of SCAN_DIRS) {
  const full = join(PROJECT_ROOT, target);
  let st;
  try { st = statSync(full); } catch { continue; }
  const files = st.isDirectory() ? [...walk(full)] : [full];
  for (const file of files) {
    const rel = relative(PROJECT_ROOT, file).replaceAll("\\", "/");
    if (!shouldScan(rel)) continue;
    let text;
    try { text = readFileSync(file, "utf8"); } catch { continue; }
    const lines = text.split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      for (const { needle, hint } of MOJIBAKE) {
        if (lines[i].includes(needle)) {
          hits.push({ file: rel, line: i + 1, needle, hint, snippet: lines[i].trim().slice(0, 80) });
        }
      }
    }
  }
}

if (hits.length === 0) {
  console.log(`lint:utf8: 0 mojibake sites in ${PROJECT_ROOT}`);
  process.exit(0);
}

console.error(`lint:utf8: ${hits.length} mojibake site(s) found:`);
for (const h of hits) {
  console.error(`  ${h.file}:${h.line}: ${JSON.stringify(h.snippet)}`);
  console.error(`    mojibake ${JSON.stringify(h.needle)} → real ${h.hint}`);
}
console.error("");
console.error("Fix: re-save the file as UTF-8 (no BOM) and replace the mojibake bytes");
console.error("     with the real Unicode character. See BBF-4 / BBF-5 closure memos.");
process.exit(1);
