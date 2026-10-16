# BBF-doc-drift-flip — flip 14 stale `Status: OPEN` FU entries in OPEN-FOLLOWUPS.md to RESOLVED

**Sprint intent:** Doc-only BBF. Audit every "OPEN"
follow-up in `docs/16_audit/OPEN-FOLLOWUPS.md` against
the actual code state on `main@cab74655`. For each FU
whose fix is durable on main, flip the ledger entry's
`Status` line from `OPEN` (or `IN PROGRESS`, `PARTIAL`,
or unmarked) to `RESOLVED <date> via <commit/PR>` with
the closure evidence. Out of scope: FUs whose fixes
have not actually landed (genuinely OPEN; tracked
separately).

**Identified:** 2026-10-16, surfaced by the session's
honest pre-flight during the `go FU-34` directive
(which turned out to be already closed at `2c92fda4`,
PR #117) and the `go FU-10` directive (also already
closed at `2a6276bd`, PR #83). Both pre-flights
surfaced the same systemic issue: **the ledger has
drifted from the code state**. Many FU entries say
"Status: OPEN" but the actual fix is on main with CI
green. This BBF consolidates those drifts.

**The 14 FUs to flip to RESOLVED:**

| # | FU | Fix commit / PR | Verification |
|---|---|---|---|
| 1  | FU-7  | `ee292874` (BBF-FU-11c, PR TBD) — α route opt-in to stored per-player book | PARTIAL — α shipped; Tier 2+ deferred |
| 2  | FU-8  | `aee6038e` — fix(deps): FU-8 remove dead narration-context plumbing (Option A) | dead-code removed |
| 3  | FU-10 | `2a6276bd` (PR #83) — fix(deps): FU-10 pin h2 >= 4.4.1 to close CVE-2026-71554 | `h2==4.4.1` in `uv.lock`; pip-audit green on `cab74655` |
| 4  | FU-12 | `74cab77b` (PR #123) — chore(deps): pnpm-workspace.yaml overrides (nanoid, dompurify, js-yaml) | overrides clear the vulps; pnpm-audit green on `cab74655` |
| 5  | FU-16 | `77a83796` (PR #89) — fix(tests): FU-16 ProfileDashboard async-data test fix | ProfileDashboard test passes |
| 6  | FU-17 | `20792f48` (PR #87) — fix(deps): FU-17 durable pnpm pin via packageManager + corepack | `packageManager: pnpm@11.21.0` in `apps/desktop/package.json` |
| 7  | FU-28 | `f0b07dac` (PR TBD) — feat(ci): enforce-by-default for backend tests | CI now enforces backend tests |
| 8  | FU-31 | `042f56c1` (PR #111) — fix(tests): rewrite test_route_is_wired_to_smoke_yml | meta-test rewritten for glob convention      |
| 9  | FU-32 | `b4a8e5f0` (PR #112) — fix(route): add os.path.isdir() pre-check | `os.path.isdir` pre-check added              |
| 10 | FU-33 | `fd984efd` (PR #113) — docs(OPEN-FOLLOWUPS): resolve FU-33 as accepted | commit-body amend deferred |
| 11 | FU-38 | `1dbf59e8` (PR #140) — gitleaks allowlist for 27 pre-existing findings | 12/12 CI green on `cab74655` |
| 12 | FU-39 | `47062dfa` (PR #138) — gitleaks-action v2 → v3 | 12/12 CI green |
| 13 | FU-40 | `3f056c6f` (PR #139) — smoke.yml 17 action pins to @v6 | 12/12 CI green |
| 14 | FU-41 | `cab74655` (PR #141) — security-audit.yml 6 final Node-20 pins to @v6 | 12/12 CI green |

Each flip is a `Status: OPEN` → `Status: RESOLVED <date>
via <sha> (<PR>)` change near the top of the existing
FU section, plus an explanatory `## Resolved` cross-reference.

**The 13 FUs explicitly excluded** (genuinely still OPEN; not in scope):

| # | FU | Why still open |
|---|---|---|
| 1  | FU-5  | IN PROGRESS — branch `bbf-fu5-pv-moves-san` still WIP |
| 2  | FU-6  | 3 narration tests; no fix commit |
| 3  | FU-9  | Long-term v2 narrative-gold corpus; awaiting curator |
| 4  | FU-11 | Phase 2 trigger; not blocking α |
| 5  | FU-19 | A-F11 PDF sandbox has no test |
| 6  | FU-20 | A-F11 prop 2 (network isolation) — no implementation |
| 7  | FU-21 | A-F11 prop 3 (read-only FS) — no implementation |
| 8  | FU-22 | A-F11 prop 4 (2GB mem cap) — no implementation |
| 9  | FU-23 | DEFERRED UNTIL PHASE 8 (data-dir migration) |
| 10 | FU-27 | explicitly NO ACTION this session (per directive 2026-08) |
| 11 | FU-29 | Declared-but-unused quality tooling (ruff/mypy/pytest-cov) |
| 12 | FU-30 | Non-portable hardcoded path in `tests/perf/conftest.py:57` (log only) |
| 13 | FU-35 | `services/chess_coach/__init__.py` still missing; PyInstaller blocks |

These 13 will remain in the `## FU-N` section with
their existing `Status: OPEN` (or equivalent) markers.
The BBF's diff is restricted to the 14 closures only.

**Work product:**

This BBF produces 2 file changes:

1. `docs/16_audit/OPEN-FOLLOWUPS.md` (modified,
   +N lines) — for each of the 14 FUs, prepend a
   `**Status:** RESOLVED <date> via <sha> (<PR>)` line
   (or change the existing `OPEN` / `IN PROGRESS` /
   `PARTIAL` line to the RESOLVED form) with a
   one-paragraph closure note citing the fix commit
   and the post-fix verification (e.g. "h2==4.4.1 in
   `uv.lock`; pip-audit green on `cab74655`"). For
   FU-7 specifically, the flip is to `PARTIAL` with
   "α shipped in BBF-FU-11c; Tier 2+ deferred to
   Phase 2 trigger" rather than full RESOLVED.
2. `docs/16_audit/BBF-doc-drift-flip.md` (NEW, 153
   lines) — this brief.

**Out of scope (NOT in this BBF):**

- The 13 genuinely-open FUs listed above. Each has its
  own BBF to-do (some have explicit "deferred" status;
  some have no fix commit and need separate work).
- The "FU-37 phantom" referenced in 3 prior commit
  messages (9791dafc, 8f79469c, 660e1172). FU-37 is
  not a real FU entry; this BBF does not invent one.
- Any new functional change to the codebase. This BBF
  is doc-only; it does not add code, tests, or
  workflow changes.

**Honest disclosures:**

- **The `## Resolved` section** at the bottom of
  `OPEN-FOLLOWUPS.md` is **NOT** updated by this BBF.
  The 14 flipped entries each carry their own inline
  `**Status:** **RESOLVED ...**` line at the top of
  their existing section (mirroring the FU-18 doc-drift
  pattern). A future cross-reference BBF could add
  the 14 entries to the `## Resolved` summary table
  if desired; that is out of scope here.
- **FU-7's "PARTIAL" status** is preserved (not flipped
  to full RESOLVED). The α route opt-in is shipped; the
  Tier 2+ persistent support is still deferred to Phase 2
  per the FU-7 entry's existing "Phase 2 trigger"
  language. This BBF documents the partial state, not
  declares it done.
- **The 12/12 CI green on `cab74655`** is the cross-FU
  verification: pip-audit (FU-10), pnpm-audit (FU-12,
  FU-17), gitleaks (FU-38), smoke.yml (FU-40), security-
  audit.yml (FU-41), and gitleaks-action (FU-39) are all
  on the same `cab74655` commit. Single-CI-run verification
  for all 7 CI-touching FUs.
- **The σ-gate footgun risk** is real: each flip adds
  `path:N` references (e.g. `uv.lock`, `tests/perf/conftest.py:57`).
  Per the v0.7.128 (σ) discipline, all such refs are
  wrapped in inline backticks. Pre-commit verification
  via `python scripts/dev/verify_commit_refs.py
  --commit-body "..."` returns "No file:line references
  found" on the staged diff.
- **Byte-integrity:** 0 literal U+2019 in the new
  content. The existing 4 U+2019 in `OPEN-FOLLOWUPS.md`
  are preexisting in HEAD and are not touched by this
  BBF.
- **CRLF footgun:** the new brief is written via the
  `write_file` tool (which preserves LF on Windows).
  The `OPEN-FOLLOWUPS.md` edits are made via the `patch`
  tool which preserves the file's existing line endings.
  No LF/CRLF regression expected.

**Hermes verification (re-derive, post-merge):**

- For each of the 14 FUs flipped, the closure evidence
  is cited inline: fix commit SHA + post-fix verification
  result. Cross-checkable via `git show <sha>` and the
  existing CI check-run IDs.
- `git show main:docs/16_audit/OPEN-FOLLOWUPS.md | grep
  "^## FU-" | head -50` shows all 14 flipped entries
  with their new `Status: RESOLVED` lines; the 13
  excluded entries retain their `Status: OPEN` (or
  equivalent) markers.
- 12/12 CI green on the new BBF's amended SHA.

**Final report format:** the squash-merge commit body
documents the 14-flip scope + the 13-excluded list + the
+lines/0-files-touched-elsewhere stat. The commit body
uses inline-backtick-wrapped `path:N` references where
appropriate and paraphrases where not, per the v0.7.128
(σ) discipline.
