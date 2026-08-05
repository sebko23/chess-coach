#!/usr/bin/env node
/**
 * Codegen wrapper for apps/desktop/src/services/coach/api.ts.
 *
 * Drives the chess-coach backend's OpenAPI schema -> openapi-typescript ->
 * apps/desktop/src/services/coach/api.ts regeneration.
 *
 * Pipeline (per FU-4 BBF, 2026-08-04):
 *   1. Run `python scripts/dev/export_openapi.py` to produce `.openapi.json`.
 *   2. Run `openapi-typescript <absolute-path>/.openapi.json -o <tmp>`.
 *      Absolute paths are required because `npx openapi-typescript` resolves
 *      relative paths against apps/desktop/ (the package directory), not the
 *      caller's CWD.
 *   3. If --check is passed, diff the regenerated file against the committed
 *      one; exit non-zero if they differ (CI verification mode).
 *
 * Usage:
 *   pnpm gen:api           # regenerate api.ts
 *   pnpm gen:api:check     # verify api.ts matches what would be regenerated
 *
 * Both modes require `openapi-typescript` to be installed (devDep) and the
 * chess-coach Python package to be importable (the script invokes the
 * `chess_coach.gateway.app.create_app()` function).
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..", "..");

const args = process.argv.slice(2);
const checkOnly = args.includes("--check");

function runOrDie(cmd, cmdArgs, label) {
  const result = spawnSync(cmd, cmdArgs, {
    cwd: repoRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) {
    console.error(`FAIL: ${label} exited with status ${result.status}`);
    process.exit(result.status ?? 1);
  }
}

// Step 1: regenerate .openapi.json (the export script writes to <repoRoot>/.openapi.json).
console.log("[gen-api] step 1/2: exporting OpenAPI schema...");
// Use `python` from PATH. CI uses actions/setup-python@v5 which puts the
// runner's Python on PATH; pip install -e '.[dev]' installs into that
// interpreter's site-packages. There is NO project-local venv in CI,
// so a hardcoded .venv/bin/python path would silently fail with
// spawnSync result.status === null (ENOENT on exec).
//
// Local dev: PATH `python` may resolve to the Hermes agent venv
// instead of the project venv. To avoid that, callers can run
// `node scripts/codegen/gen-api.mjs` from a shell where `python`
// resolves to the project interpreter (e.g. activate `.venv`
// first, or use a venv-aware shell).
// Resolve the Python interpreter to use. Strategy:
//   1. If `.venv/bin/python` (Linux) or `.venv/Scripts/python.exe`
//      (Windows) exists, use it (project-local venv, the local-dev
//      convention).
//   2. Otherwise, fall back to `python` from PATH. CI uses this -- the
//      actions/setup-python@v5 Python is on PATH and pip installs into
//      its site-packages; there is no project-local venv in CI.
//
// The hardcoded `.venv` path is resolved via existsSync so the same
// wrapper works in both local dev (venv) and CI (system Python) without
// any environment-variable configuration. This is the explicit
// resolution per the FU-4 BBF discipline: no 'works on my machine'
// implicit behavior, the resolution is in code.
const _projectVenvPython = process.platform === "win32"
  ? join(repoRoot, ".venv", "Scripts", "python.exe")
  : join(repoRoot, ".venv", "bin", "python");
const _useVenv = existsSync(_projectVenvPython);
const projectPython = _useVenv ? _projectVenvPython : "python";
if (!_useVenv) {
  console.log(
    "[gen-api] no project venv at " + _projectVenvPython + ";"
    + " using PATH python (CI-style install)."
  );
}
runOrDie(projectPython, ["scripts/dev/export_openapi.py"], "export_openapi.py");

// Step 2: regenerate api.ts (or compare for --check mode).
const openapiSchemaPath = join(repoRoot, ".openapi.json");
const apiTsPath = join(
  repoRoot,
  "apps",
  "desktop",
  "src",
  "services",
  "coach",
  "api.ts",
);
const tmpApiTsPath = join(repoRoot, ".api.ts.cand");

mkdirSync(dirname(tmpApiTsPath), { recursive: true });

console.log(`[gen-api] step 2/2: running openapi-typescript...`);
// Invoke openapi-typescript directly via its node_modules/.bin shim. Using npx
// with --no-install fails because the package lives in apps/desktop/node_modules
// (pnpm layout), not in a global location npx searches by default.
const openapiTypescriptBin = join(
  repoRoot,
  "apps",
  "desktop",
  "node_modules",
  ".bin",
  "openapi-typescript" + (process.platform === "win32" ? ".cmd" : "")
);
runOrDie(
  openapiTypescriptBin,
  [openapiSchemaPath, "-o", tmpApiTsPath],
  "openapi-typescript",
);

if (checkOnly) {
  if (!existsSync(apiTsPath)) {
    console.error(
      `FAIL: ${apiTsPath} does not exist. Run \`pnpm gen:api\` first to create it.`,
    );
    process.exit(1);
  }
  // Normalize line endings: openapi-typescript emits LF; the committed
  // api.ts may be CRLF (per project convention). Compare semantically
  // by stripping carriage returns from both before comparing.
  const committed = readFileSync(apiTsPath, "utf8").replace(/\r\n/g, "\n");
  const candidate = readFileSync(tmpApiTsPath, "utf8").replace(/\r\n/g, "\n");
  if (committed === candidate) {
    console.log("[gen-api] OK: api.ts is up-to-date with the backend schema.");
    process.exit(0);
  } else {
    console.error(
      "[gen-api] FAIL: api.ts is stale relative to the backend schema. " +
        "Run `pnpm gen:api` to regenerate it, then commit the updated api.ts.",
    );
    process.exit(1);
  }
} else {
  const candidate = readFileSync(tmpApiTsPath, "utf8");
  writeFileSync(apiTsPath, candidate);
  console.log(`[gen-api] OK: wrote regenerated api.ts to ${apiTsPath}`);
}