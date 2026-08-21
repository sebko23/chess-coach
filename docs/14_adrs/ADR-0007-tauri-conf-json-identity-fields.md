# ADR-0007: Tauri config identity fields (binary-distribution metadata)

- **Status**: proposed
- **Date**: 2026-08-20
- **Deciders**: project owner
- **Consulted**: (none external; this ADR formalizes an already-accepted posture from `LICENSING.md` §55-57 + `ADR-0004` against a specific config surface, rather than resolving a novel legal question)

## Context

CHESS COACH GUI at `apps/desktop/` is a fork of [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant), pinned to upstream commit `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53` per `apps/desktop/.upstream-ref`. The fork relationship is governed by `docs/15_integration_surfaces/en-croissant.md` (the integration contract) and `apps/desktop/UPSTREAM.md` (the binding attribution record). The license posture is governed by `ADR-0004` and mirrored in `LICENSING.md`.

The Tauri config file at `apps/desktop/src-tauri/tauri.conf.json` ships six upstream-identity fields that identify the binary to the OS installer, the package manager, and the auto-updater:

| Field | Current value (upstream identity) | Surface |
|---|---|---|
| `bundle.publisher` | `"Francisco Salgueiro"` | Windows MSI / NSIS `Publisher` field; macOS `SignerName` |
| `bundle.shortDescription` | `"Ultimate Chess Toolkit"` | OS installer metadata |
| `productName` | `"en-croissant"` | Display name in OS menus, installer dialogs, app launcher |
| `mainBinaryName` | `"en-croissant"` | Executable filename on disk |
| `identifier` | `"org.encroissant.app"` | Reverse-DNS bundle identifier; used by macOS code-signing, auto-updater endpoints |
| `plugins.updater.endpoints[0]` (line 64 of `tauri.conf.json`: `"https://www.encroissant.org/updates"`) — Tauri v2 schema | upstream update server | Auto-updater endpoint |

These fields ship in the binary *as installed by users*. The Phase 8 minimum-viable scoping brief (`docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md` §3.1, lines 214-230, byte-verified against `origin/main` blob 19515 bytes LF) flagged the en-croissant metadata in `tauri.conf.json` as a "legal/license blocker, not a knowledge blocker" and presented three options: (a) renaming + republishing with proper attribution, (b) dual-binary strategy, (c) explicit GPL acknowledgment + keeping the en-croissant attribution prominent.

The integration contract `docs/15_integration_surfaces/en-croissant.md` §3.1 allowlists edits to `tauri.conf.json` for *additive* allowlist entries (window-creation, fs read, http to loopback) with the constraint "Existing entries untouched." §9 of the same document requires that any change to §3.1 reference an ADR.

`LICENSING.md` §55-57 ("Trademark and attribution," counsel-informed via `ADR-0004`) has already settled the *posture*:

> "We retain upstream copyright notices in modified files within `apps/desktop/`. We do not claim endorsement by en-croissant or its author. The CHESS COACH brand is distinct from en-croissant; we credit en-croissant in the 'About' dialog and in `apps/desktop/README.md`."

That paragraph already picks option (a)'s substance ("distinct brand, credit via About dialog + README"). What it does not specify is which *specific fields* of which *specific files* carry the brand identity vs. the attribution credit. This ADR resolves that application.

## Decision

This ADR formalizes the field-level application of `LICENSING.md` §55-57 + `ADR-0004`'s posture to `apps/desktop/src-tauri/tauri.conf.json`'s six identity fields:

1. **The six `tauri.conf.json` identity fields are brand-identity fields, not attribution-credit fields.** They identify the binary as "CHESS COACH" for OS installation, package management, auto-updater, and code-signing purposes. Changing them to CHESS COACH brand values implements `LICENSING.md` §55-57's "distinct brand" half.

2. **The attribution credit to en-croissant is *not* carried by these fields.** It is carried by:
   - `apps/desktop/LICENSE` (GPL-3.0, byte-identical to upstream per `apps/desktop/UPSTREAM.md` §20-22 and integration contract §7.1)
   - `apps/desktop/UPSTREAM.md` (binding attribution record, including the §109 paragraph: *"en-croissant is the original work of Francisco Salgueiro and contributors. CHESS COACH is a downstream fork. We are not affiliated with or endorsed by en-croissant or its author."*)
   - The "About" dialog in `apps/desktop/src/components/About.tsx` (where the en-croissant upstream URL is currently linked; the credit mechanism there is out of scope for this ADR but the attribution chain runs through it)
   - `apps/desktop/README.md` attribution block

3. **The integration contract §3.1 allowlist is extended by this ADR** to permit changes to the six identity fields listed in §"Context" above. The "Existing entries untouched" constraint in §3.1's row for `tauri.conf.json` covers the capability-allowlist entries explicitly named in §3.1 (window-creation, fs read for `backend.json`, http to loopback only); by reasonable extension of the same rule, it also covers the `capabilities` block, the `bundle.linux` / `bundle.macOS` blocks that configure packaging per-OS, and the `build` block's `beforeDevCommand` / `beforeBuildCommand` / `frontendDist` / `devUrl`. The "Existing entries untouched" rule does **not** apply to the six identity fields named in §"Context," which are upstream's brand, not upstream's behavior. (This ADR's reading of the "Existing entries untouched" rule to cover the additional blocks beyond §3.1's literal letter is explicit: the alternative reading — that "Existing entries untouched" only applies to the three explicitly named entries — would still produce the same outcome for the six identity fields.)

4. **The LICENSE byte-identity requirement (integration contract §7.1) is unaffected by this ADR.** `apps/desktop/LICENSE` remains byte-identical to upstream. Future CI enforcement (`tools/ci/check_forbidden_paths.py`, to be authored in Phase 1) will continue to assert this.

5. **New field values** (CHESS COACH brand identity):
   - `bundle.publisher`: the project owner's chosen publisher name (currently TBD; `LICENSING.md` §55-57 references "CHESS COACH" generically; project owner to provide a specific name at implementation time, defaulting to `"Chess Coach"` if no other value is chosen)
   - `bundle.shortDescription`: a CHESS COACH-specific one-line description (TBD; defaulting to `"Chess analysis and training with grounded narration"` if no other value is chosen)
   - `productName`: `"Chess Coach"`
   - `mainBinaryName`: `"chess-coach"` (matches the Python package's CLI entry-point name and the repo root name)
   - `identifier`: a reverse-DNS identifier for the project (TBD; defaulting to `"org.chesscoach.app"` if no other value is chosen — this requires that no other application has claimed that identifier on macOS / Windows code-signing registries)
   - `plugins.updater.endpoints[0]` (or the relevant URL field): a CHESS COACH-specific update endpoint (TBD; *cannot be set to a non-existent server*, since the auto-updater will fail to fetch updates). Implementation must either (i) point at a real CHESS COACH release server, (ii) comment out / disable the auto-updater until a server exists, or (iii) leave the URL pointing at the upstream server with the explicit understanding that CHESS COACH users will receive upstream en-croissant updates until a CHESS COACH release server is in place. The implementation BBF for PR #100 must surface this trade-off to the user before merging; this ADR does not pre-decide it.

6. **The implementation BBF (separate from this ADR) is responsible for:**
   - confirming the chosen `identifier` does not collide with another registered macOS / Windows app
   - setting up a code-signing certificate (separate concern; per Phase 8 brief §3.3, this is a separate cost/identity blocker, not in scope here)
   - verifying the chosen update endpoint is reachable (or disabling auto-update)
   - leaf-review of the per-field change with byte-level integrity checks per the post-2026-08-13 byte-verification discipline (`git show HEAD:path`, `git show FETCH_HEAD:path` after force-push)

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| Leave `tauri.conf.json` identity fields as upstream en-croissant | Zero work; respects §3.1 letter | Every installed binary identifies as "en-croissant" / "Francisco Salgueiro" / "Ultimate Chess Toolkit"; violates `LICENSING.md` §55-57's "distinct brand" requirement | `LICENSING.md` §55-57 is already an accepted posture |
| Dual-binary strategy (option (b) in Phase 8 brief) | Two parallel identities (en-croissant and CHESS COACH) preserved | Requires shipping two binaries with different identity metadata; doubles installation, code-signing, and update-surface work; doesn't reflect the project owner's already-accepted "distinct brand, single binary" posture in `LICENSING.md` | `LICENSING.md` §55-57 already prefers a single distinct brand |
| Keep en-croissant attribution prominent in `publisher` / `identifier` (option (c) in Phase 8 brief) | Lowest-risk attribution approach | Violates `LICENSING.md` §55-57's separation of "distinct brand" from "attribution mechanism"; attribution belongs in the README/About dialog/license, not in the OS-installer metadata | `LICENSING.md` §55-57 already separates brand identity from attribution credit |
| Rename identity fields to chess-coach values (this ADR's choice) | Implements `LICENSING.md` §55-57; minimal surface; LICENSE byte-identity preserved; attribution chain unaffected | Requires new identifier / publisher name; requires decision on update endpoint; requires a follow-up ADR or BBF for any change to fields *not* in this ADR's §Context table (see §"Scope explicitly excluded" below) | None — this is the chosen path |

## Consequences

### Positive

- Binary identifies as CHESS COACH on every supported platform (Windows MSI / NSIS, macOS .app, Linux AppImage / .deb), implementing `LICENSING.md` §55-57's "distinct brand" requirement.
- Attribution to en-croissant remains intact via the LICENSE byte-identity + UPSTREAM.md + README + About dialog chain, none of which this ADR touches.
- The integration contract §3.1 allowlist extension is explicitly scoped to the six identity fields; the "Existing entries untouched" rule for capability / build / OS-packaging configuration is reaffirmed.
- The "About" dialog and README credit mechanism (`LICENSING.md` §55-57) is named as the *actual* attribution vehicle, so the post-implementation review can verify attribution is preserved where it is intended.

### Negative / accepted tradeoffs

- Changing `identifier` from `org.encroissant.app` to a new reverse-DNS string is a one-way door: macOS code-signing and Windows package identity use the identifier for update endpoints, file associations, and cross-app coordination. Existing en-croissant users who migrate to CHESS COACH will need to uninstall the old binary first.
- The update-endpoint decision (point at new server, point at upstream temporarily, or disable auto-update) is a runtime / infrastructure decision this ADR does not pre-resolve. The implementation BBF must surface it.
- `tauri.conf.json` is a single JSON file; this ADR does not extend to other upstream-identity surfaces in the fork (see §"Scope explicitly excluded" below). Those are separate BBFs.

### Scope explicitly excluded (each is a separate BBF, named here so the surface is visible)

| File | Field | Why excluded from this ADR |
|---|---|---|
| `apps/desktop/src-tauri/Cargo.toml` | `name`, `authors`, `repository` | The Rust crate's package metadata. `name` is coupled to `Cargo.lock`'s package name and is mechanical; `authors` is an authorship-claim field with different semantics than GUI distribution metadata; `repository` is a source-code pointer (informational). Changing `authors` from `["Francisco Salgueiro <fgcdbs@gmail.com>"]` to a CHESS COACH author has implications this ADR does not pre-resolve. Separate BBF. |
| `apps/desktop/package.json` | `name` | npm-style package identifier; mechanical to change but coupled to `pnpm-lock.yaml` and any tooling that depends on the package name. Separate BBF. |
| `apps/desktop/src-tauri/src/main.rs` | log file name `"en-croissant.log"` | Runtime log file path on user disk. Renaming it is a backward-compatibility consideration for users upgrading from the upstream binary. Separate BBF. |
| `apps/desktop/src-tauri/src/oauth.rs` | OAuth client_id `"org.encroissant.app"` | Registered with the OAuth provider (Lichess / Chess.com). Changing it requires registering a new OAuth application with the provider; the existing client_id cannot be unilaterally changed. Separate BBF + external registration action. |
| `apps/desktop/src/utils/http.ts` | `APP_NAME`, `APP_REPO` | Used by the auto-updater / update-check client. Coupled to the update endpoint decision (see Decision §5). Separate BBF. |
| `apps/desktop/src/utils/directories.ts` | default data directory `"EnCroissant"` | User's local data dir on disk. Renaming it is a backward-compatibility consideration for users upgrading from the upstream binary. Separate BBF + migration path. |
| `apps/desktop/src/utils/db.ts` | `https://www.encroissant.org/databases` | Runtime fetch of opening databases. Coupled to whether CHESS COACH operates its own database mirror. Separate BBF + external service decision. |
| `apps/desktop/src/utils/engines.ts` | `https://www.encroissant.org/engines` | Runtime fetch of engine binaries. Coupled to whether CHESS COACH operates its own engine mirror. Separate BBF + external service decision. |
| `apps/desktop/src-tauri/capabilities/main.json` | `https://www.encroissant.org/**` in domain allowlist | Tauri capability allowlist entry (the kind of entry §3.1 *does* allowlist for editing). Coupled to whether CHESS COACH operates its own update / docs / database / engine endpoints. Separate BBF, can be addressed alongside the URL-field decisions above. |
| `apps/desktop/src/routes/__root.tsx` | log file path; help link to `encroissant.org/docs/` | Help link is informational; log path is coupled to the `main.rs` log-name decision. Separate BBFs. |
| `apps/desktop/src/components/About.tsx` | `https://www.encroissant.org` link | The "About" dialog is named by `LICENSING.md` §55-57 as one of the attribution-credit vehicles. Verifying the attribution chain runs through this dialog is a follow-up action (§"Follow-up actions" below), not part of this ADR's identity-field change. |
| `apps/desktop/src/components/ErrorComponent.tsx`, `apps/desktop/.github/ISSUE_TEMPLATE/bug.yml`, `apps/desktop/CONTRIBUTING.md` | upstream issue-tracker / PR-comparison links | Out-of-binary documentation pointers; informational only; not user-facing in the installed binary. Separate doc-only cleanup BBF if desired. |
| `apps/desktop/src/components/settings/SettingsPage.tsx` and 28 translation files | `Settings.Anarchy.ForcedEnCroissant` / `.Desc` strings | "En Croissant" is a real chess opening name (a chess rule for forcing en passant capture), not a brand reference. These strings must NOT be changed by a rebrand. Out of scope by correctness — they would be wrong to change. |
| `apps/desktop/src/state/atoms/coach.ts` | comments referencing en-croissant's zustand `TreeStore` | Code comments naming upstream's internal state structure. Informational; the comments are accurate as long as the bridge from upstream's `TreeStore` is in place. Separate cosmetic cleanup if desired. |
| `apps/desktop/src-tauri/Cargo.lock` | `name = "en-croissant"` for the package itself | Regenerable from `Cargo.toml` `name`. Addressed in the `Cargo.toml` BBF, not here. |
| `apps/desktop/src-tauri/icons/*` | All icon assets are upstream's iconography | Visual rebrand is a design-decision BBF, separate from any config-field change. Out of scope here. |
| `apps/desktop/LICENSE` | (GPL-3.0 byte-identical) | MUST remain byte-identical. Out of scope by integration contract §7.1. |
| `apps/desktop/UPSTREAM.md` | (binding attribution record) | MUST be preserved as-is per integration contract §1 and §3.1's `apps/desktop/UPSTREAM.md` row. Out of scope here. |
| `apps/desktop/README.md` | Attribution block at §15-17 | The attribution credit vehicle named by `LICENSING.md` §55-57. The README is currently stale (says "Status: not yet populated. Phase 1 implementation will fork en-croissant..." but the fork DID happen on 2026-05-18 per `UPSTREAM.md`). Stale-README cleanup is a separate doc-only BBF. The attribution block itself is unaffected by this ADR; it stays as the attribution-credit mechanism. |

### Follow-up actions

- **(this ADR)** After acceptance, the implementation BBF (PR #100 or its successor) addresses the six `tauri.conf.json` fields per §"Decision" above, with byte-level integrity verification per the post-2026-08-13 discipline.
- **(separate doc-only BBF)** Refresh `apps/desktop/README.md` to reflect post-fork reality (remove "Status: not yet populated" line; update fork-date citation to `2026-05-18`; preserve the §15-17 attribution block verbatim). This is a doc-drift cleanup, not an attribution-chain change.
- **(separate code-touch BBF)** Implement an explicit "About" dialog credit mechanism (per `LICENSING.md` §55-57): a CHESS COACH "About" dialog screen that credits en-croissant by name and links to its repository. This implements the "About dialog credit" half of `LICENSING.md` §55-57 that is *not* currently implemented in the GUI. (`About.tsx` currently has an upstream-URL link but is not a dedicated credit dialog.)
- **(separate BBF per excluded scope item)** Each row in §"Scope explicitly excluded" above is a future BBF with its own scoping decision; this ADR does not pre-decide any of them.
- **(CI enforcement, Phase 1 per `LICENSING.md` §55-57 follow-ups)** Add a CI assertion that the LICENSE byte-identity check passes (Phase 1, per `tools/ci/check_forbidden_paths.py` per integration contract §7.1). This is unaffected by the present ADR but is named here because the LICENSE byte-identity check is the load-bearing mechanism that keeps the attribution chain intact independently of any binary-identity changes.

## References

- `docs/15_integration_surfaces/en-croissant.md` §1 (upstream baseline), §3.1 (allowlist — extended by this ADR for the six fields in §"Context"; the §3.1 `tauri.conf.json` row's "Preserve verbatim" instruction for `apps/desktop/LICENSE` is reaffirmed unchanged by this ADR), §3.2 (never-edit list — the 8 items in the never-edit list are unchanged; the LICENSE byte-identity requirement is governed by §3.1's "Preserve verbatim" row + §7.1 below, NOT by §3.2), §7.1 (LICENSE byte-identity check — unaffected by this ADR), §9 (ADR requirement for §3.1 changes — this ADR)
- `docs/14_adrs/ADR-0004-license-posture.md` (the accepted license posture; this ADR formalizes its application to `tauri.conf.json`)
- `LICENSING.md` §55-57 (Trademark and attribution; the posture this ADR formalizes)
- `apps/desktop/UPSTREAM.md` (binding attribution record; unaffected by this ADR)
- `apps/desktop/.upstream-ref` (machine-readable upstream pin `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53`; unaffected by this ADR)
- `apps/desktop/LICENSE` (GPL-3.0 byte-identical; unaffected by this ADR)
- `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md` §3.1 lines 214-230 (the Phase 8 brief's framing of this question as a legal/license blocker with three options; this ADR formalizes option (a))
- `apps/desktop/src-tauri/tauri.conf.json` lines 26-50, 64 (the six fields this ADR scopes)
