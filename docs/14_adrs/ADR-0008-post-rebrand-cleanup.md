# ADR-0008: Post-rebrand cleanup of upstream-inherited files (log filenames, dead GitHub config, upstream links)

- **Status**: proposed
- **Date**: 2026-08-22
- **Deciders**: project owner
- **Consulted**: (none external; this ADR covers cosmetic cleanup of upstream-inherited files after the PR #101 identity-field rebrand, per the integration contract §3.3 ask-first rule)

## Context

PR #101 (BBF-100) changed six `tauri.conf.json` identity fields to CHESS COACH values (`productName`, `mainBinaryName`, `identifier`, `publisher`, `shortDescription`; removed `plugins.updater`). ADR-0007's §Scope explicitly excluded table named 17 upstream-inherited surfaces deferred to separate BBFs. This ADR covers the *cosmetic cleanup subset* — items that are self-contained string/link fixes or dead-config deletions with no coupling to build tooling, package registries, or external services:

1. **Log filename strings** (`apps/desktop/src-tauri/src/main.rs:197` and `apps/desktop/src/routes/__root.tsx:288`): both hardcode `"en-croissant.log"`. After PR #101 changed `identifier` to `org.chesscoach.app`, Tauri's `appLogDir()` returns the NEW identifier-derived directory (`%APPDATA%\org.chesscoach.app\logs\`) while the filename still says `"en-croissant.log"` — producing `%APPDATA%\org.chesscoach.app\en-croissant.log`. The two references must change together: `__root.tsx:288` resolves `appLogDir()` + the same hardcoded filename to build the path used by the GUI's log-viewer menu item; if only one changes, the menu opens a nonexistent file.

2. **Dead GitHub config** (5 files under `apps/desktop/.github/`): verified via GitHub Actions API (`GET /repos/sebko23/chess-coach/actions/workflows` returns only root `.github/workflows/smoke.yml` and `security-audit.yml`; no workflow under `apps/desktop/.github/` has ever been registered). GitHub reads issue templates, funding config, and workflows ONLY from the repository-root `.github/` directory; these 5 files can never fire:
   - `FUNDING.yml`: directs donations to upstream author (`buy_me_a_coffee: franciscosal`) — actively misattributed for this fork
   - `ISSUE_TEMPLATE/bug.yml`: routes users to upstream's issue tracker; dead regardless
   - `ISSUE_TEMPLATE/improvement.yml`: same shape; dead
   - `workflows/release.yml`: full Tauri release pipeline referencing secrets `TAURI_PRIVATE_KEY` / `TAURI_KEY_PASSWORD` that this repo does not have configured; never registered; actively misleading (looks like a working pipeline)
   - `workflows/test.yml`: dead file — never registered with Actions (verified via API), so it never ran; its lint+vitest steps are NOT currently provided by root `smoke.yml`'s frontend jobs either (a pre-existing frontend-CI gap logged for a follow-up BBF)

3. **Upstream issue-tracker link** (`apps/desktop/src/components/ErrorComponent.tsx:46`): the error screen's "Report an issue" anchor routes users to `franciscoBSalgueiro/en-croissant/issues/new` — filing chess-coach bug reports into upstream's tracker. Root `CONTRIBUTING.md` L10 documents the contribution entry point as the GitHub issues page ("**Issues**: see the GitHub issues page"); this repository has GitHub Issues enabled (`has_issues=true`) with no existing upstream contamination.

All three items are upstream-inherited files NOT in §3.1's allowlist. §2's blanket rule ("we do not edit existing en-croissant files except the small allowlist in §3") plus §3.3's ask-first rule require this ADR before any edit. None of the items touch the chess-engine UCI wrapper (§3.2's never-edit list) — the log-filename strings are logging configuration, not engine logic; the GitHub config files are not engine-related; ErrorComponent.tsx is a UI component.

## Decision

1. **Rename both log-filename strings** from `"en-croissant.log"` to `"chess-coach.log"` (main.rs:197 and __root.tsx:288, atomically in one commit).
2. **Delete all 5 files under `apps/desktop/.github/`** — dead config that cannot fire, including one file (FUNDING.yml) that is actively misattributed and one (release.yml) that is actively misleading.
3. **Retarget the `ErrorComponent.tsx:46` issue link to this repository's tracker** — replace the `<Trans>` block's `github:` Anchor href (`franciscoBSalgueiro/en-croissant/issues/new?...template=bug.yml`) with `https://github.com/sebko23/chess-coach/issues/new`. The `<github>` component tag itself is unchanged (32 translation files interpolate it; changing the destination, not the component, keeps every translation valid). The Discord anchor at L50 stays untouched pending confirmation that upstream's server hosts a chess-coach channel (open editorial question).

The implementation BBF executes all three decisions in one pass after this ADR merges.

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| Keep dead config "for reference" | Zero effort | FUNDING.yml misattributes donations; release.yml misleads future contributors into thinking a release pipeline exists; dead config accumulates noise that obscures live config | Misleading artifacts are worse than absent ones |
| Rewrite apps/desktop/.github/* configs to chess-coach values instead of deleting | Preserves structure for future use | GitHub will never read them from that path; maintaining dead files is wasted effort; if chess-coach wants issue templates later, they must be created at ROOT .github/ anyway (different location, different content needs) | Dead code/config should be deleted, not maintained |
| Remove the ErrorComponent link entirely or point it at CONTRIBUTING.md only | Avoids implying a bug-report workflow the project may not staff | This repository has GitHub Issues enabled (`has_issues=true`) and root `CONTRIBUTING.md` L10 names the GitHub issues page as the entry point — a working, chess-coach-owned destination already exists; removing the link would leave users with nowhere to go | Retargeting to the existing tracker preserves the user path with one line changed and keeps all 32 translations valid |
| Do nothing (leave all three as-is) | Zero risk | Log filename inconsistency grows every session the app runs; FUNDING.yml keeps misdirecting donations; ErrorComponent keeps sending bug reports upstream | These are real user-facing wrongnesses, not theoretical ones |

Note on translation-file count: the `<github>` component tag is interpolated by 32 translation JSON files (the earlier "33" figure included `ErrorComponent.tsx` itself).

## Consequences

### Positive

- Log files land at `%APPDATA%\org.chesscoach.app\logs\chess-coach.log` — directory AND filename consistent post-rebrand.
- No misleading dead config in the tree; future contributors see only live CI configuration.
- Chess-coach users no longer directed to file bugs on upstream's tracker.

### Negative / accepted tradeoffs

- Deleting `release.yml` removes a template that Phase 8 packaging might have adapted. Counter-argument: Phase 8 will design its own release pipeline against actual requirements (signing certs, update server), not reuse unregistered upstream config; the file remains recoverable from git history if needed.
- Removing the upstream-issue link leaves a gap until chess-coach stands up its own tracking surface. Counter-argument: CONTRIBUTING.md already documents the actual workflow.

### Follow-up actions

- Implementation BBF: execute all three decisions in one commit after this ADR merges.
- If Phase 8 later needs a release workflow, author it fresh against actual signing/update requirements (not adapted from the deleted upstream file).

## Scope explicitly excluded (not this ADR)

- `Cargo.toml` / `package.json` / `Cargo.lock` package identity fields → ADR-0009 (separate decision: different semantics — package/build-tooling identity vs. cosmetic cleanup).
- `icons/*` visual rebrand → design-decision BBF.
- OAuth client_id re-registration → external Lichess/Chess.com action.
- FU-23 data-dir migration → Phase 8-gated.
- `LICENSE`, `UPSTREAM.md` → never edit (integration contract §7.1 / §3.1).
- `SettingsPage.tsx` + translation files (`ForcedEnCroissant` chess opening name) → never touch (not brand references).
- `coach.ts` comments → lowest priority; informational; accurate as-is.

## References

- `docs/15_integration_surfaces/en-croissant.md` §2 (blanket no-edit rule), §3.3 (ask-first rule), §9 (ADR requirement) — the governance basis for this ADR
- `docs/14_adrs/ADR-0007-tauri-conf-json-identity-fields.md` — the rebrand whose leftovers this ADR cleans up; §Scope explicitly excluded rows 3, 10, 12 (ErrorComponent group), and the doc-only-upstream-inherited row
- PR #101 (`d2016db9`) — the identifier change that made the log filename inconsistent
- Root `CONTRIBUTING.md` L10 — names the GitHub issues page as the contribution entry point
