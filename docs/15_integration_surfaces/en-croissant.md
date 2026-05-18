# Integration Surface — en-croissant (the GUI fork)

**Status**: binding for Phase 1 and all subsequent phases.
**Owner**: project owner (changes require an ADR).
**Related**: `docs/13_review_response/legal-protocol-assessment-received.md`, `docs/14_adrs/ADR-0004-license-posture.md`, `LICENSING.md`, `BUILDING.md`, `specs/v1.0/chess-coach-protocol-v1.md`.

## Why this document exists

Counsel's verdict on the GPL-3.0 §5 aggregate question (preserved in `docs/13_review_response/legal-protocol-assessment-received.md`) cleared the *legal* design. This contract clears the *engineering* design. Specifically: it documents exactly what we touch and what we leave alone in the [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant) fork, so that:

1. The boundary asserted on paper is verifiable in code at every commit.
2. Upstream en-croissant rebases remain mechanically tractable indefinitely.
3. A reviewer (us, counsel, a third party) can confirm in minutes that the project is operating within the boundary it has chosen.

If this contract is broken, the GPL aggregate position weakens. Treat it accordingly.

---

## 1. Upstream baseline

The fork is taken from en-croissant at a **pinned upstream commit**, recorded in:

- `apps/desktop/UPSTREAM.md` — human-readable record of the upstream URL, commit hash, tag if any, fork date, and a verbatim copy of upstream's `LICENSE`, `README`, and any `NOTICE` files.
- `apps/desktop/.upstream-ref` — machine-readable: a single line containing the upstream commit hash. Read by CI to verify the rebase tooling stays consistent.

The upstream commit is chosen as the most recent release tag (or the most recent stable commit if no tag is current) at fork time. Phase 1 will set it explicitly; this contract does not bind the value.

---

## 2. What we add (the "coach surface")

All CHESS COACH-specific code lives in **clearly delimited additive directories**. We do not edit existing en-croissant files except for the small allowlist in §3.

### 2.1 New directories (additive — no upstream content)

| Path | Purpose |
|---|---|
| `apps/desktop/src/panels/coach/` | All CHESS COACH React panels. Each subdirectory is one panel (analysis, narration, training, profile, etc.). |
| `apps/desktop/src/services/coach/` | TypeScript client for the backend (auto-generated from `specs/v1.0/`) and the WebSocket multiplex layer. |
| `apps/desktop/src/stores/coach/` | Zustand stores for CHESS COACH state. Never imports from en-croissant's existing state. |
| `apps/desktop/src/lib/coach/` | Utilities specific to CHESS COACH (e.g. grounded-narration UI primitives). |
| `apps/desktop/src/locales/coach/` | i18n strings for CHESS COACH UI. |
| `apps/desktop/src-tauri/src/coach/` | Tauri Rust-side helpers specific to CHESS COACH (descriptor-file watcher, backend handle). |

Any file added by us anywhere in `apps/desktop/` outside `src/panels/coach/`, `src/services/coach/`, `src/stores/coach/`, `src/lib/coach/`, `src/locales/coach/`, or `src-tauri/src/coach/` requires explicit owner approval and an ADR.

### 2.2 File-header convention

Every file we author in the new directories begins with:

```ts
// SPDX-License-Identifier: GPL-3.0-only
// CHESS COACH addition — © 2026 [PROJECT ENTITY]. Part of the GUI binary (GPL-3.0-only inheritance).
```

This isn't strictly required by GPL-3.0 but it makes the boundary trivially auditable.

---

## 3. What we modify in upstream files (the **edit allowlist**)

We edit upstream en-croissant files **only** for the surgical hooks listed below. Anything else is an upstream contribution path (we should send it back to en-croissant) or it belongs in our additive directories.

### 3.1 Allowed upstream edits

| Upstream file | Allowed edit | Reason |
|---|---|---|
| `apps/desktop/src/App.tsx` (or the equivalent root route file at fork time) | Add a `<CoachProviders>` wrapper and one new top-level route segment for our panels. No other changes. | We need one mount point; this is the minimum-viable one. |
| `apps/desktop/src/components/MainLayout.tsx` (or equivalent layout file) | Add a slot for the CHESS COACH side panel. Existing slots untouched. | The coach panel needs visibility. |
| `apps/desktop/src-tauri/tauri.conf.json` | Add coach-specific allowlist entries (window-creation, fs read for `backend.json`, http to loopback only). Existing entries untouched. | Tauri capabilities are config-driven; we cannot avoid editing this file. |
| `apps/desktop/package.json` | Add coach-specific dependencies and scripts. Existing entries untouched except for keeping dependency versions in sync with upstream. | npm metadata file; cannot avoid editing. |
| `apps/desktop/src-tauri/Cargo.toml` | Same as `package.json` but for Rust. | Same reason. |
| `apps/desktop/README.md` | Replace with our README; preserve a clear "Forked from en-croissant" attribution block at top. | The product is no longer en-croissant; users need to know what they have. |
| `apps/desktop/LICENSE` | Preserve verbatim. | en-croissant is GPL-3.0-only; we inherit. Never edit. |

### 3.2 What we never edit

- The chess engine UCI wrapper (`apps/desktop/src-tauri/src/...` engine-related files in upstream).
- The board rendering layer (`apps/desktop/src/components/Board*` and any chessground integration).
- The opening book and database files.
- Existing analysis panels.
- The existing PGN parser.
- The existing settings UI (we add settings via our own panel that posts to the backend; we never read or write en-croissant's settings store from our code).
- Any test files.
- Any localization files outside our `locales/coach/`.

CI enforces this via a forbidden-paths check (§ 7.1).

### 3.3 The "if you need to edit upstream, ask first" rule

If during Phase 1 implementation we discover that the allowed edits in §3.1 are insufficient (e.g. the layout slot can't accept a new panel without a structural change), we **stop** and write an ADR before touching anything new. We do not silently expand the allowlist.

---

## 4. Communication with the Backend

### 4.1 Single boundary

The GUI calls the Backend **only** through `apps/desktop/src/services/coach/client.ts` (the TypeScript client) and `apps/desktop/src/services/coach/ws.ts` (the WebSocket multiplex). No upstream code calls the Backend directly.

Client code is auto-generated from `specs/v1.0/schemas/` at build time. Hand-edits to the generated client are forbidden; instead, edit the spec or the Pydantic models in `libs/protocol_types/` (which produce the schemas).

### 4.2 Connection discovery

The GUI reads `backend.json` from `${CHESS_COACH_DATA_DIR}/runtime/` per spec §1.4. If the file is missing, the GUI displays a clear "Backend not running" screen with a button to launch the bundled sidecar (or instructions to start it manually in dev builds). The GUI **never** falls back to embedded analysis logic; if the Backend is unavailable, coach features are simply absent and the underlying en-croissant features remain available.

### 4.3 Token handling

The `session_token` is read from `backend.json` and held only in memory. It is never persisted by the GUI, never logged, and never displayed in any UI. On `401 Unauthorized` the GUI re-reads `backend.json` and reconnects (spec §2).

### 4.4 Loopback only

The GUI **only** connects to `127.0.0.1` (or `::1`). Even if `backend.json` lists a non-loopback host, the GUI refuses and surfaces an error. (A future LAN/remote mode would require its own ADR and a different connection-discovery path.)

---

## 5. State boundary

- en-croissant's Zustand/Recoil/whatever state is **read-only** from coach code. Coach code may *read* upstream state (e.g. "what's the current FEN on the board?") through small read-only selector functions we add to `src/services/coach/upstream-readers.ts`. Coach code never *writes* to upstream state.
- Coach state is held in `src/stores/coach/` stores. Upstream code never imports from these.
- If upstream needs a piece of coach state (e.g. "is the coach analysis panel open?") and we ever genuinely need to wire it back, that's an ADR-worthy event and a sign that the boundary is bending.

---

## 6. Upstream rebase workflow

At least quarterly (and immediately for upstream security fixes), we rebase the fork on the latest en-croissant.

### Procedure

1. `git fetch upstream && git checkout -b rebase/<date>-<upstream-commit>`
2. `git rebase upstream/main` (or the appropriate upstream branch)
3. Resolve conflicts. Conflicts in upstream files we did not edit should never occur (if they do, our forbidden-paths CI check has been wrong; fix it). Conflicts in upstream files we did edit (§3.1) are resolved minimally, preserving our edits as additions rather than replacements where possible.
4. Update `apps/desktop/.upstream-ref` and `apps/desktop/UPSTREAM.md` to record the new baseline.
5. Run the full conformance suite + en-croissant's own test suite if it has one.
6. Open a PR titled `chore(desktop): rebase onto en-croissant <commit>`.

If a rebase becomes painful (more than ~30 minutes of conflict resolution), that is itself a signal: our edit allowlist may be too broad. Open an ADR to discuss narrowing.

---

## 7. CI enforcement

### 7.1 Forbidden-paths check

A CI job (`tools/ci/check_forbidden_paths.py`, to be authored in Phase 1) walks the git diff between `HEAD` and `upstream/main` for every PR and verifies that:

- No upstream files are edited except those in §3.1.
- No new files are added in `apps/desktop/` outside the §2.1 directories.
- The `apps/desktop/LICENSE` file is byte-identical to upstream.
- The `apps/desktop/.upstream-ref` file's referenced commit exists in the upstream remote.

The job fails the build if any check fails.

### 7.2 Header check

A CI job verifies that every TypeScript / Rust file we added in §2.1 carries the SPDX-License-Identifier + attribution block from §2.2.

### 7.3 Connection check

A CI job runs the GUI in headless mode and asserts that it makes no network connection to anything other than `127.0.0.1` and `::1` during a representative startup + shutdown cycle.

### 7.4 No-binary-identity-check check

A CI job runs the GUI in headless mode against (a) the signed build and (b) a self-built unsigned build, with the same Backend, and asserts behavior is identical. This guards binding architectural commitment P2 (§6 anti-tivoization).

---

## 8. Things we deliberately do not do

- **No FFI between GUI and Backend.** Both processes communicate only over the public protocol.
- **No shared schema files between GUI and Backend.** The TS client and Pydantic models are *both* generated from the same source-of-truth (the JSON Schemas in `specs/v1.0/schemas/`), but the schemas are public spec files, not implementation-private files. A third party can use them identically.
- **No "helpful" Tauri commands that wrap Backend behavior.** Every Backend call goes through the standard HTTP/WS path. No native Tauri-command shortcuts.
- **No silent fallback to in-GUI analysis if the Backend is down.** Coach features are simply unavailable.
- **No license-header rewriting of upstream files.** We preserve upstream copyright notices verbatim.

---

## 9. Changes to this contract

This contract changes only via ADR. Any PR that proposes a change to §2.1, §3.1, §3.2, or §7 must reference an open or merged ADR in `docs/14_adrs/`.

Deprecating a rule (e.g. relaxing the "no FFI" stance) is itself a change requiring an ADR; we don't drift by quiet accretion.
