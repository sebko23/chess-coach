# BBF-FU-45 — wire the UTF-8 mojibake guard into CI

**Date:** 2026-10-25
**Branch:** `bbf-fu-45-wire-utf8-guard`
**Base:** `18df358f4abd249468e7cf8cce91d09cafb51249` (`main`)

## Objective

The repository has contained a UTF-8 mojibake guard since BBF-17 that has
**never run in any CI job**. Its own header, and three tracked documents,
claimed otherwise. This BBF makes the guard real and corrects the claims.

## Finding

`scripts/lint-utf8.mjs` (repository root) is a guard that flags the classic
"UTF-8 bytes decoded as Latin-1 and re-encoded as UTF-8" mojibake — the mistake
that produced `â†'`, `â€¦`, `Â·` in `CoachPanel.tsx`, `GameDetailPage.tsx`, and
`ProfileDashboard.tsx` during the BBF-4 / BBF-5 sprints.

It was **orphaned**:

| Claim | Reality |
|---|---|
| `// Run via: pnpm lint:utf8` | no `lint:utf8` script exists in `apps/desktop/package.json` |
| `// Wired into: pnpm lint:ci` | `lint:ci` did not reference it |
| `CONTRIBUTING.md`: "**Pre-commit hook**: every commit runs `lint-utf8.mjs`" | no pre-commit hook exists — no `.git/hooks/pre-commit`, no `.husky/`, no `core.hooksPath`. The base `CONTRIBUTING.md` said nothing about the hook either way; it simply asserted one existed |
| `docs/REPO-READINESS.md` §6: "The **pre-commit** UTF-8 lint … **blocks any non-ASCII character**" | wrong twice: there is no pre-commit hook, and the guard flags a **fixed list of 10 mojibake sequences**, not arbitrary non-ASCII |

It was also **mis-located**. `PROJECT_ROOT = process.cwd()` and
`SCAN_DIRS = ["src", "scripts", "i18next.config.ts", "index.html"]`, so the guard
only scans `apps/desktop/src/` when the cwd is `apps/desktop`. From the
repository root — where it lived — it scanned nothing relevant. `pnpm lint:ci`
runs from `apps/desktop`.

Verified: `git grep` found no reference to `lint-utf8` in
`.github/workflows/smoke.yml` or `.github/workflows/security-audit.yml`.

## Changes

### 1. The guard moves to where it can actually run

`git mv scripts/lint-utf8.mjs apps/desktop/scripts/lint-utf8.mjs` — a pure
rename (identical blob SHA before the content edit), landing it
beside `check-i18n-keys.mjs`, the sibling guard that *is* wired.

### 2. `apps/desktop/package.json` — the wiring

```json
"lint:ci": "node scripts/lint-utf8.mjs && tsgo --noEmit && oxfmt --check && oxlint --format=github && node scripts/check-i18n-keys.mjs",
"lint:utf8": "node scripts/lint-utf8.mjs",
```

`lint:ci` is what the `frontend lint + test` CI job runs
(`.github/workflows/smoke.yml`), so the guard is now enforced on every PR. It is
prepended so a mojibake finding short-circuits before the slower steps.

**No CI workflow file is modified.** The guard is reached through the existing
`pnpm lint:ci` invocation — the same shape as the already-wired
`check-i18n-keys.mjs`.

### 3. Three tracked documents corrected

`CONTRIBUTING.md` and `docs/REPO-READINESS.md` §6 now describe what actually
happens: the guard runs **in CI** via `pnpm lint:ci` (not in a pre-commit
hook), and it flags a **fixed list of mojibake sequences** rather than blocking
arbitrary non-ASCII. The `docs/`, `libs/`, `tests/` exclusion statement in
REPO-READINESS §6 was verified correct and is retained.

`docs/CHANGELOG.md` carried two further live claims in present tense — the
BBF-62 entry ("runs as a pre-commit hook") and the BBF-17 section ("is still in
place and runs on every commit"). Both are now stated as what was recorded at
the time, with the correction that the guard never ran in a pre-commit hook and
was in no CI job until this BBF. The BBF-27 entry's mention of a "pre-commit
UTF-8 hook" is a historical record of what that sprint's `CONTRIBUTING.md`
said, and is deliberately left as written.

### 4. `apps/desktop/scripts/lint-utf8.mjs` — header corrected + `oxfmt`-formatted

The header's two false claims are corrected and the scan scope is stated
explicitly. Moving the file into `apps/desktop/` brought it into `oxfmt`'s
scope, so it was formatted with `oxfmt` (29 insertions / 9 deletions across 7
rewrite sites; on the base file alone `oxfmt` takes it from 93 to 113
newline-terminated lines). **The detection logic is unchanged**: all 10
`MOJIBAKE` needles are byte-identical before and after (verified by codepoint
comparison), and the guard's behaviour was re-verified empirically after the
reformat.

## Regression test

`tests/unit/test_lint_utf8_guard.py` — 7 tests.

**Why Python and not vitest:** `apps/desktop/src/` is browser-only by design.
There is no `@types/node` in `devDependencies`, and **no** file under
`apps/desktop/src/` imports a Node builtin. `tsgo --noEmit` fails any test file
that does. `vitest`'s include glob is `src/**/*.{test,spec}.{ts,tsx}`, so there
is no in-frontend location for a Node-API test. The precedent for testing a
frontend scanner from the Python suite is
`tests/unit/test_check_frontend_imports.py` (BBF-67).

| Test | Purpose |
|---|---|
| `test_guard_detects_mojibake_and_exits_nonzero` | detection regression |
| `test_guard_allows_legitimate_non_ascii` | wiring it in cannot break the tree on real Unicode |
| `test_guard_scans_the_scripts_directory_too` | the `scripts/` half of the scan scope |
| `test_guard_lives_beside_the_frontend_scripts` | it must not remain at the repo root |
| `test_guard_is_wired_into_package_json_and_ci` | positive wired-assertion: `lint:utf8` exists, `lint:ci` invokes it, a CI job runs `pnpm lint:ci` |
| `test_this_test_file_is_enforced_by_ci` | positive wired-assertion for this file: `tests/unit` is globbed AND this path is not in any `--ignore=` |
| `test_no_literal_mojibake_in_this_file` | the test must not itself contain literal mojibake |

### Negative testing (mandatory, per the FU-31 caveat)

Every condition was mutated to confirm the meta-test **fails closed**:

| Mutation | Expected | Result |
|---|---|---|
| `lint:ci` no longer invokes the guard | fail | **PASS** (exit 1) |
| `lint:utf8` script removed | fail | **PASS** (exit 1) |
| CI job no longer runs `pnpm lint:ci` | fail | **PASS** (exit 1) |
| this file added to the coverage job's `--ignore=` | fail | **PASS** (exit 1) |

The fourth case initially **passed when it should have failed**. The coverage
job's pytest invocation is a single long line, so the original line-anchored
`--ignore=` regex never matched a mid-line flag. The assertion now scans the
whole invocation with `--ignore=(\S+)` after stripping YAML comment lines,
which also prevents a commented-out flag from producing a false positive. This
is the FU-31 comment-noise caveat in a new costume.

## Verification (all with the CI's exact commands)

| Gate | Command | Result |
|---|---|---|
| Python tests | CI coverage invocation (`--cov-fail-under=55`) | exit 0 — **540 passed**, 9 skipped (533 baseline + 7 new) |
| Python lint | `ruff check libs services apps/cli tests scripts` | exit 0 — all checks passed |
| Python types | `mypy libs services apps/cli --no-incremental --platform linux` | exit 0 — no issues in 86 source files |
| Frontend lint | `pnpm lint:ci` (guard now first) | exit 0 — 0 errors, 81 pre-existing warnings, i18n gate OK |
| Frontend tests | `pnpm test` (vitest) | exit 0 — 7 files, 44 passed |
| Frontend format | `oxfmt --check` (via `lint:ci`) | exit 0 — all matched files correctly formatted |

The 9 pytest skips and 81 oxlint warnings are pre-existing.

## Scope

8 files: the guard (moved + header + format), `package.json`, three documents
(`CONTRIBUTING.md`, `docs/REPO-READINESS.md`, `docs/CHANGELOG.md`), one new test
file, this brief, and `docs/16_audit/OPEN-FOLLOWUPS.md` — which carries the
FU-45 ledger entry as a pure insertion.

## Deliberately out of scope

- **The two orphan `.bak` files** — `apps/desktop/src/components/panels/coach/CoachPanel.tsx.bak_1780860511`
  (16,855 bytes) and `services/chess_coach/gateway/routes/repertoire_recommendations.py.bak`
  (5,999 bytes). Both are referenced by nothing, and neither is identical to
  the live file. They are a separate cleanup, not part of the wiring.
  **Correction (2026-10-26, FU-47):** both were added by a 2026-06-13
  commit titled "backup: pre-player-atom state snapshot before shared atom
  migration", and `cd43906c` merely carried them forward; the original
  attribution came from a shallow clone whose history boundary was
  `cd43906c`. That cleanup BBF has since landed.
- **The `.gitattributes` / CRLF root cause.** 17 tracked TEXT files genuinely
  contain CRLF in their committed blobs. A further 49 binary assets contain
  CRLF byte values incidentally, and 108 tracked files contain a 0x0D byte at
  all, but a byte-value coincidence inside a PNG is not a line-ending defect.
  That is a separate BBF needing per-extension review for binary formats
  (32 `.png`, 32 `.jpg`, 24 `.mp3`, 2 `.ico`, 1 `.icns`).
- **No pre-commit hook was added.** The repo does not install one — no
  `.git/hooks/pre-commit`, no `.husky/`, no `core.hooksPath`. Adding one would
  be a new mechanism, not a correction of a false claim.
