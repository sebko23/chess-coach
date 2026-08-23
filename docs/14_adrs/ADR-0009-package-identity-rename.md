# ADR-0009: Package identity rename (Cargo.toml, package.json, Cargo.lock)

- **Status**: proposed
- **Date**: 2026-08-22
- **Deciders**: project owner
- **Consulted**: (none external; registry-collision checks performed via public npm + crates.io APIs during scoping)

## Context

PR #101 (BBF-100) changed the Tauri bundle identity fields to CHESS COACH values, but the *package-level* identities remain upstream's:

- `apps/desktop/src-tauri/Cargo.toml`: `name = "en-croissant"`, `authors = ["Francisco Salgueiro <fgcdbs@gmail.com>"]`, `repository = "https://github.com/franciscoBSalgueiro/en-croissant"`
- `apps/desktop/package.json`: `"name": "en-croissant"`, `"version": "0.15.0"` (upstream's version, not ours)
- `apps/desktop/src-tauri/Cargo.lock`: contains the matching `name = "en-croissant"` entry (regenerable from Cargo.toml)

This differs in kind from ADR-0008's cosmetic cleanup: package names are **build-tooling and ecosystem identity** — they affect Rust crate naming, npm package semantics, potential future publishing, and how the project presents itself to both ecosystems.

### Registry-collision investigation (performed 2026-08-22)

Neither name is published on either registry:

| Registry | `en-croissant` | `chess-coach` |
|---|---|---|
| npm (`registry.npmjs.org`) | NOT PUBLISHED (404) | NOT PUBLISHED (404) |
| crates.io | NOT PUBLISHED (API: "crate does not exist") | NOT PUBLISHED (API: "crate does not exist") |

Methodology note (recorded because the first pass had a false negative risk):
crates.io's initial API response was HTTP 403 (rate-limit/bot-blocking), which is
NOT the same as a not-found result. The definitive check re-queried the API with
a browser-formatted User-Agent and received explicit JSON error bodies:
`{"errors":[{"detail":"crate \`en-croissant\` does not exist"}]}` and the same for
`chess-coach`, plus a positive control (`serde` → 200, published) proving the
method works. Note that checking via the human-facing HTML pages
(`crates.io/crates/<name>`) is unreliable — the site serves an HTTP 200 SPA shell
for any URL, including obviously nonexistent names.

The coupling risk ADR-0007 hypothesized ("coupled to `pnpm-lock.yaml`") does not exist: `pnpm-lock.yaml` contains ZERO occurrences of "en-croissant" (verified via git grep). The lockfile references packages by their resolved registry names, and since this package was never published, no lockfile entries depend on the current name.

Blast radius for a rename (verified via git grep at `origin/main@d2016db9`):
- `"name": "en-croissant"` appears only in `package.json` itself
- `name = "en-croissant"` appears in `Cargo.toml`, `Cargo.lock` (regenerable), and ADR docs (historical record, unchanged)
- No build scripts, CI workflows, or runtime code reference the package name as an identifier

## Decision

1. **Rename the Rust crate** in `Cargo.toml`: `name = "en-croissant"` → `name = "chess-coach"`. Regenerate `Cargo.lock` (mechanical; verified regenerable).
2. **Update Cargo.toml metadata**: `authors` → the CHESS COACH project's own authorship attribution (exact value TBD by project owner at implementation time; must not claim upstream's authorship); `repository` → the chess-coach repository URL.
3. **Rename the npm package** in `package.json`: `"name": "en-croissant"` → `"name": "chess-coach"`.
4. **Decide version handling**: `package.json` currently carries upstream's `"version": "0.15.0"`. Options at implementation time: (a) reset to `0.1.0` (fresh versioning for the fork's GUI), or (b) keep tracking upstream versions until divergence makes that meaningless. This ADR does not pre-decide; implementation BBF surfaces the choice with the project owner's input recorded in its commit body.
5. **Verify no downstream breakage**: after rename, run the full frontend verification suite (tsgo, vitest, lint) and confirm root CI remains green.

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| Keep upstream package names indefinitely | Zero effort; zero risk of breaking tooling | Every surface of the project would say "en-croissant" while every other identity says CHESS COACH; contradicts LICENSING.md §55-57's distinct-brand posture; confuses future contributors | Inconsistent with the completed rebrand |
| Rename crate but keep npm name | Halves the work | Arbitrary split — both are equally local-only (neither is published); partial renames recreate the inconsistency being fixed | Half-measures extend the cleanup tail |
| Rename both (this ADR's choice) | Completes the rebrand across all surfaces; registry checks confirm no collision; blast radius verified small | Requires one coordinated commit + full frontend verification | None — chosen path |

## Consequences

### Positive

- Package identity matches every other post-rebrand identity surface.
- Future npm/crates publishing (if ever desired) starts from correct names.
- Cargo.lock regeneration is mechanical and verifiable.

### Negative / accepted tradeoffs

- Anyone with a stale local clone referencing the old crate name will need a clean rebuild (lockfile change). Dev-environment-only concern; no end-user installs exist (Phase 8 has never shipped).
- Upstream rebase workflow (integration contract §6) becomes slightly more complex for Cargo.toml (our name/authors/repository lines will conflict on every rebase). Counter-argument: §3.3 anticipates this — conflicts in files we've edited are resolved minimally, preserving our edits.

### Follow-up actions

- Implementation BBF: execute the rename + lockfile regen + full frontend verification in one commit after this ADR merges.
- If Phase 8 packaging later publishes to any registry, verify the chosen names are still available at publish time (registry state can change).

## Scope explicitly excluded (not this ADR)

- Log filenames, dead GitHub config, ErrorComponent link → ADR-0008 (cosmetic cleanup; separate review timeline)
- `icons/*`, OAuth client_id, FU-23 migration → unchanged exclusions per ADR-0007
- Tauri `productName` / `mainBinaryName` / `identifier` → already done in PR #101 (ADR-0007)

## References

- `docs/15_integration_surfaces/en-croissant.md` §2, §3.3, §9 — governance basis
- PR #101 (`d2016db9`) — the Tauri-side rebrand this ADR complements
- npm + crates.io API queries performed 2026-08-22 (both names unpublished)
