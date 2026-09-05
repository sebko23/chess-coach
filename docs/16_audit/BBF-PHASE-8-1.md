# BBF-Phase8-1 — PyInstaller spec for the chess-coach-gateway binary

**Status:** implemented on branch `bbf-phase-8-pyinstaller-spec`, awaiting merge
**Author:** Hermes session 2026-09-04
**Parent:** `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md`

## Scope

First BBF of the Phase 8 minimum-viable installer effort. The brief
identified this BBF as: "write `chess-coach-backend.spec`, figure out the
hidden-imports for the namespace layout, produce a working `.exe` from
`pyinstaller`."

Per the brief and session-investigation findings:

- **Entry point:** `chess_coach.gateway.__main__:main` (per `pyproject.toml:68`)
- **Hidden imports:** `chess` (python-chess; lazy-imported in 4 top-level sites
  + 1 function-local site; PyInstaller's analysis often misses guarded
  top-level imports)
- **Data files:** 9 .sql migration files at
  `libs/chess_coach/storage/migrations/` (loaded at runtime via
  `importlib.resources.files()` in `storage/migrate.py:70`)
- **Excludes:** `torch`, `sentence_transformers`, `transformers` — the FU-4
  lazy-import keeps these out of the gateway startup; excluding them keeps
  binary size manageable. KB functionality (`/v1/kb/similar`,
  `/v1/kb/index`) is unavailable in this binary. Documented as
  intentional.
- **Smoke test scope:** `/v1/system/health` only. Does NOT exercise KB,
  engine analysis, or `/v1/profiles/explain` (which reads a hardcoded
  relative path to a docs file that's not in the bundle).

## Files shipped

| File | Purpose |
|---|---|
| `services/chess_coach/gateway/chess-coach-gateway.spec` | PyInstaller spec, `--onefile` mode, target name `chess-coach-gateway` |
| `tests/integration/test_pyinstaller_binary.py` | Smoke test: builds the binary via PyInstaller CLI, spawns it as a subprocess, polls `/v1/system/health` until 200, asserts response shape, tears down |
| `.github/workflows/smoke.yml` | New `pyinstaller-binary-smoke` CI job that runs the above on `ubuntu-latest`. Also adds `--ignore=tests/integration/test_pyinstaller_binary.py` to the existing `gateway-boot` job's pytest invocation so the binary-building test doesn't run in the source-test job (it needs PyInstaller which the gateway-boot job doesn't install). |

## Verification (what CI proves when this lands)

1. The spec compiles successfully (PyInstaller's static analysis completes).
2. The Binary builds without missing-import errors (hidden imports list catches all 5 `chess` sites).
3. The Binary starts and serves `/v1/system/health` on `127.0.0.1` within 30 s.
4. The health response includes `status: ok` and a non-empty `backend_version`.

## What this BBF does NOT do (deferred to subsequent BBFs)

- **BBF-Tauri-sidecar:** update `tauri.conf.json` with `externalBin` for the
  binary, add a Rust command that spawns the sidecar, wire into JS layer.
- **BBF-Build-and-bundle:** drop `--no-bundle` from `package.json` so
  `tauri build` produces an MSI/NSIS installer.
- **BBF-Sidecar-smoke:** full end-to-end smoke that includes the Tauri shell.
- **BBF-Sidecar-distribution-doc:** document what shipped, what didn't
  (Stockfish bundled? Qdrant? Memurai?), next-step options.
- **Bundle `profile-metrics-v1.md` for `/v1/profiles/explain`** so the
  endpoint returns methodology text instead of the "Methodology doc not
  found" error.
- **Re-introduce KB functionality in the sidecar** by removing the
  `torch`/`sentence_transformers` excludes (binary size will balloon by
  ~600 MB; this is a deliberate tradeoff to defer).
- **Windows artifact:** the brief's default is option (a.ii) — documented
  manual build on a Windows machine. Adding a `windows-latest` runner
  is a separate BBF.

## Known limitations flagged for spec iteration

1. `/v1/profiles/explain` will return an error message "Methodology doc not
   found" in the PyInstaller bundle until either docs bundling is added
   or the path resolution is rewritten. The smoke test does NOT exercise
   this endpoint.
2. Stockfish path defaults to agent-Zero-specific
   `/usr/local/bin/stockfish` (per `services/chess_coach/gateway/app.py:135`)
   with PATH fallback. The smoke test runs on `ubuntu-latest` where
   Stockfish is NOT installed; the engine pool falls back to PATH
   lookup, which also won't find it — the binary should still start
   because engine pool init is non-fatal. This matches the existing
   `gateway-boot` CI job which exercises the gateway without engine
   binaries.

## Pre-implementation investigation summary

Six conditional-import sites investigated in `services/chess_coach/` and
`libs/chess_coach/`. Five lazy-import `chess` (python-chess) inside
`try/except ImportError` blocks; one is FU-4's deferred
`sentence_transformers` import inside `kb/embedder.py:_get_model()` (which
PyInstaller's analysis does NOT follow). No `importlib.import_module` or
`__import__()` usage anywhere in the codebase. The start-list
`hiddenimports=['chess']` covers all five sites in one entry.

## Provenance

- Source basis: byte-reads against `origin/main@4c30a7b7`.
- Brief: `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md`
- ADR-0007 / ADR-0008 / ADR-0009 (identity-field rebrand): all merged as
  PRs #100–#104; rebrand prerequisites cleared before this BBF.