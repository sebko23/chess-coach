#!/usr/bin/env node
// i18n key-coverage gate (FU-25 follow-up, Option B — zero-edit).
//
// NEVER writes to apps/desktop/src/translation/ (contract §3.2 protected).
//
// How it works:
//   1. Generates a sandbox copy of i18next.config.ts whose `output:` is
//      redirected into node_modules/.cache/, runs `i18next-cli extract`
//      there, and reads the GENERATED en-US key set — the canonical
//      "which keys does the source reference" truth.
//   2. Parses the COMMITTED en-US file read-only.
//   3. STRICT: fails if any source-referenced key is missing from
//      committed en-US. This is the app's real fallback contract
//      (index.tsx: `fallbackLng: "en-US"`): a key present in en-US
//      resolves for every locale; a key absent from en-US renders raw
//      everywhere. That is the regression class the original
//      `extract --ci` gate existed to catch.
//   4. ADVISORY: lists source-referenced keys missing from secondary
//      locales (e.g. the fork's never-backfilled SideBar.* strings).
//      Secondary gaps fall back to en-US at runtime by design; backfilling
//      them requires contract §3.2 governance and is NOT this gate's job.
//
// Rationale (2026-08-24): direct `i18next-cli extract --ci` rewrites the
// protected files and destroys ~96% of stored values, because the
// extractor cannot read the legacy {"translation": {...}} wrapper shape
// (nsSeparator:false makes "translation" an opaque key). Until a
// value-preserving migration path is proven on copies, this gate provides
// the coverage protection without touching protected content.
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import process from "node:process";

const DESKTOP_ROOT = fileURLToPath(new URL("..", import.meta.url));
const CONFIG_PATH = path.join(DESKTOP_ROOT, "i18next.config.ts");
const COMMITTED_DIR = path.join(DESKTOP_ROOT, "src", "translation");
const CACHE_DIR = path.join(DESKTOP_ROOT, "node_modules", ".cache", "i18n-keygate");
const OUTPUT_ANCHOR = 'output: "src/translation/{{language}}.json"';
const MAX_LISTED = 20;

function flattenKeys(node, prefix, out) {
  for (const [k, v] of Object.entries(node)) {
    const key = prefix === "" ? k : `${prefix}.${k}`;
    if (v !== null && typeof v === "object") {
      flattenKeys(v, key, out);
    } else {
      out.add(key);
    }
  }
}

function loadKeys(filePath) {
  const doc = JSON.parse(readFileSync(filePath, "utf8"));
  // Legacy shape wraps everything in a "translation" namespace object;
  // nsSeparator:false means a literal top-level "translation" KEY cannot
  // exist in these files, so this unwrap is unambiguous.
  const root = doc.translation !== undefined ? doc.translation : doc;
  const keys = new Set();
  flattenKeys(root, "", keys);
  return keys;
}

let exitCode = 0;
try {
  const configText = readFileSync(CONFIG_PATH, "utf8");
  if (!configText.includes(OUTPUT_ANCHOR)) {
    console.error(
      `[i18n-keygate] ERROR: expected "${OUTPUT_ANCHOR}" not found in ${CONFIG_PATH}.`,
      "\nThe gate redirects this exact line into a sandbox directory;",
      "if the config moved, update OUTPUT_ANCHOR in scripts/check-i18n-keys.mjs.",
    );
    process.exit(2);
  }
  const primaryMatch = configText.match(/primaryLanguage:\s*"([^"]+)"/);
  if (!primaryMatch) {
    console.error("[i18n-keygate] ERROR: could not read primaryLanguage from", CONFIG_PATH);
    process.exit(2);
  }
  const primary = primaryMatch[1];

  // Locate the installed CLI's JS entry directly (no .cmd shim, no shell).
  const require = createRequire(import.meta.url);
  const pkgJson = require("i18next-cli/package.json");
  const binField = typeof pkgJson.bin === "string" ? pkgJson.bin : pkgJson.bin["i18next-cli"];
  if (!binField) {
    console.error("[i18n-keygate] ERROR: i18next-cli package.json has no bin entry.");
    process.exit(2);
  }
  const cliJs = path.join(DESKTOP_ROOT, "node_modules", "i18next-cli", binField);

  // Sandbox config: identical to the project config except output target.
  const resourcesDir = path.join(CACHE_DIR, "resources");
  const redirectedOutput =
    'output: "' + path.join(resourcesDir, "{{language}}.json").split(path.sep).join("/") + '"';
  mkdirSync(resourcesDir, { recursive: true });
  const sandboxConfigPath = path.join(CACHE_DIR, "gate.config.ts");
  writeFileSync(sandboxConfigPath, configText.replace(OUTPUT_ANCHOR, redirectedOutput));

  const result = spawnSync(
    process.execPath,
    [cliJs, "extract", "-c", sandboxConfigPath, "--quiet"],
    { cwd: DESKTOP_ROOT, encoding: "utf8", timeout: 180_000 },
  );
  if (result.error || result.status !== 0) {
    console.error("[i18n-keygate] ERROR: extractor run failed.");
    if (result.stdout) console.error(result.stdout.slice(-1500));
    if (result.stderr) console.error(result.stderr.slice(-1500));
    process.exit(2);
  }

  // Generated (source-referenced) key sets per locale.
  const generatedByLocale = new Map();
  for (const f of readdirSync(resourcesDir)) {
    if (!f.endsWith(".json")) continue;
    generatedByLocale.set(f.replace(/\.json$/, ""), loadKeys(path.join(resourcesDir, f)));
  }
  if (!generatedByLocale.has(primary)) {
    console.error(
      `[i18n-keygate] ERROR: extractor produced no file for primary locale ${primary}.`,
    );
    process.exit(2);
  }

  // Committed (protected, read-only) key sets per locale.
  const committedByLocale = new Map();
  for (const f of readdirSync(COMMITTED_DIR)) {
    if (!f.endsWith(".json")) continue;
    committedByLocale.set(f.replace(/\.json$/, ""), loadKeys(path.join(COMMITTED_DIR, f)));
  }
  const committedPrimary = committedByLocale.get(primary);
  if (!committedPrimary) {
    console.error(`[i18n-keygate] ERROR: committed primary locale file ${primary}.json not found.`);
    process.exit(2);
  }

  // STRICT: every source-referenced key must exist in committed en-US.
  const genPrimary = generatedByLocale.get(primary);
  const missingFromPrimary = [...genPrimary].filter((k) => !committedPrimary.has(k)).sort();

  // ADVISORY: secondary-locale gaps (runtime falls back to primary).
  const secondaryGaps = [];
  for (const [locale, genKeys] of [...generatedByLocale].sort()) {
    if (locale === primary) continue;
    const committed = committedByLocale.get(locale);
    if (!committed) {
      secondaryGaps.push({ locale, count: genKeys.size, sample: [] });
      continue;
    }
    const missing = [...genKeys].filter((k) => !committed.has(k));
    if (missing.length > 0) {
      secondaryGaps.push({ locale, count: missing.length, sample: missing.sort().slice(0, 5) });
    }
  }

  if (missingFromPrimary.length > 0) {
    console.error(
      "[i18n-keygate] FAIL: source-referenced key(s) missing from committed",
      `${primary}.json:`,
    );
    for (const k of missingFromPrimary.slice(0, MAX_LISTED)) console.error("   -" + k);
    if (missingFromPrimary.length > MAX_LISTED) {
      console.error(`    … and ${missingFromPrimary.length - MAX_LISTED} more`);
    }
    console.error(
      `  Total missing: ${missingFromPrimary.length}. Add the key(s) to`,
      `src/translation/${primary}.json (or remove the t() usage).`,
      "\n  This gate never edits protected files.",
    );
    exitCode = 1;
  } else {
    console.log(
      `[i18n-keygate] OK: all ${genPrimary.size} source-referenced keys exist in committed ${primary}.json.`,
    );
  }

  if (secondaryGaps.length > 0) {
    console.log(
      `[i18n-keygate] INFO: ${secondaryGaps.length} locale(s) rely on ${primary} fallback for some keys` +
        " (advisory, pre-existing):",
    );
    for (const g of secondaryGaps.slice(0, MAX_LISTED)) {
      console.log(
        `   ${g.locale}: ${g.count} key(s)` +
          (g.sample.length ? ` e.g. ${g.sample.map((k) => `"${k}"`).join(", ")}` : ""),
      );
    }
    if (secondaryGaps.length > MAX_LISTED) {
      console.log(`   … and ${secondaryGaps.length - MAX_LISTED} more locales`);
    }
  }
} finally {
  rmSync(CACHE_DIR, { recursive: true, force: true });
}
process.exit(exitCode);
