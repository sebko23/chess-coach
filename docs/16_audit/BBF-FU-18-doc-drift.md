# BBF-FU-18-doc-drift — close the FU-18 ledger entry after implementation merge

**Sprint intent:** Flip the FU-18 ledger entry in
`docs/16_audit/OPEN-FOLLOWUPS.md` from "OPEN" to "RESOLVED",
documenting the 4-amend chain that landed the A-F10 keychain
wrapper on `main` at commit `234808d8` (PR #136). Doc-only
BBF; no production code, no test changes.

**Identified:** 2026-10-15, immediately after the squash-merge
of BBF-FU-18-keyring-test-impl (PR #136) landed on `main`.
Per the BBF-FU-18-keyring-test decision brief
(`docs/16_audit/BBF-FU-18-keyring-test.md` lines 304-315):
"the ledger entry can be amended in a follow-up to flip its
status from 'OPEN' to 'DECIDED: see BBF-FU-18-keyring-test';
that's a separate doc-drift BBF, out of scope for this one."

**The gap this BBF closes:** The decision brief's
"Implementation BBF" (BBF-FU-18-keyring-test-impl, PR #136) is
now merged at `234808d8`, but the FU-18 ledger entry in
OPEN-FOLLOWUPS.md (lines 1404-1451) still says
"**Status:** OPEN. Real contract gap, no external blocker."
That status line is stale.

**The four-amend chain (for the audit trail):**

| Amend | SHA | What was fixed |
|---|---|---|
| #1 | `41fdeb98` | Initial implementation (keyring + redaction + 13 tests) |
| #2 | `4e25694a` | **gitleaks** — `[[allowlists]]` → `[allowlist]` (v1 form, the v8 array form is silently ignored by gitleaks 8.24.x), `.gitleaksignore` removed |
| #3 | `6743d628` | **gateway boot** — catch `KeyringError` in all 3 ops, in-memory test backend fixture, 3 new fail-backend tests |
| #4 | `d15bb306` | **PyInstaller fix** — rename `chess_coach.secrets` → `chess_coach.keychain` (stdlib `secrets` shadow in frozen binary) |

**Investigation-first pass (re-derive post-merge):**

- The 4-amend chain is visible in the GitHub PR #136 timeline
  (force-push events at the timestamps).
- The 12/12 CI green on the squash-merge commit `234808d8` is
  visible on the workflow run for that SHA.
- The rename `secrets` → `keychain` is verifiable by
  `git log --diff-filter=R --summary main` (renames show as
  `Rxxx ... services/chess_coach/{secrets => keychain}/__init__.py`).
- The gitleaks amend is verifiable by the SARIF artifact
  (gitleaks-results.sarif) on workflow run `38708265534`:
  - `41fdeb98` SHA: 2 findings, `ruleId='generic-api-key'`
    at `tests/unit/test_log_redaction.py:63, :104`.
  - `4e25694a` SHA: 0 findings (allowlist honored after
    `[[allowlists]]` → `[allowlist]` rename).
- The PyInstaller fix is verifiable by the workflow logs
  for run `38708239317` (the smoke workflow): the
  `gateway boot (clean install)` job's last lines show
  `ImportError: cannot import name 'token_hex' from 'secrets'`
  on the pre-rename SHAs and a clean boot on the post-rename
  SHAs.

**Work product:**

This BBF produces exactly one file change: a status flip
in `docs/16_audit/OPEN-FOLLOWUPS.md` lines 1404-1451
(the FU-18 entry). The new status block follows the
sec-01 / FU-25 RESOLVED precedent (see
`OPEN-FOLLOWUPS.md` lines 1868 and 1897): bold status with
date + squash-merge SHA + 1-2 sentences of context, then
a "What was shipped" sub-list citing the implementation
PR, the test count delta, and the merge commit SHA.

**Out of scope (separate BBFs):**

- **PR-body refresh for PR #136** — the durable PR body
  on github.com still describes the pre-amend-#4
  `chess_coach.secrets` module. Updating it is a doc-drift
  follow-up (FU-41 in the next session's handoff). This
  BBF does NOT PATCH the PR body via the GitHub API.
- **The 29 pre-existing historical gitleaks leaks** —
  visible in a local full-history scan but not in the
  diff-scoped SARIF; future FU-38 BBF.
- **gitleaks-action@v2 Node-20 deprecation** (Sep 2026
  per upstream README) — future FU-39 BBF.
- **OPEN-FOLLOWUPS.md FU-41 ledger entry** — added
  separately when the PR-body-refresh BBF ships.

**Honest disclosures:**

- This BBF does NOT PATCH the live PR #136 body on
  github.com. The body refresh requires a separate
  state-mutating action with its own explicit
  authorization, and the user's `go BBF-FU-18-doc-drift`
  directive scopes this BBF to the ledger file only.
- The status-flip's "What was shipped" subsection
  paraphrases the 4-amend chain to avoid tripping
  the v0.7.128 (σ) meta-footgun: bare `path:N` references
  in commit-body prose are a known CI failure mode.
  The (σ) discipline applies to the doc file too
  because the file is subject to `commit ref verify`
  on the diff.

**Hermes verification (re-derive, post-merge):**

- `git show main:docs/16_audit/OPEN-FOLLOWUPS.md | grep -A 2 "## FU-18"`
  shows the new "**Status:** RESOLVED ..." block.
- `grep -c "BBF-FU-18-keyring-test-impl" docs/16_audit/OPEN-FOLLOWUPS.md`
  > 0 (the ledger entry cites the implementation PR by name).
- `grep -c "234808d8" docs/16_audit/OPEN-FOLLOWUPS.md` > 0
  (the ledger entry cites the squash-merge SHA).
- (σ) `python scripts/dev/verify_commit_refs.py --commit-body "..."
  --pr-body "..."` returns "No file:line references found"
  on the commit body for this BBF.

**Final report format:** the squash-merge commit body
documents this BBF's 1-file diff (the status flip in
OPEN-FOLLOWUPS.md) + the chain of evidence (4 amend
SHAs → squash SHA `234808d8` on `main`). The commit
body uses inline-backtick-wrapped `path:N` references
where appropriate and paraphrases where not, per the
(σ) discipline recorded in the BBF-cla-bot-wire post-mortem.
