# BBF-doc-drift-flip-13 — close FU-38 as RESOLVED (accepted as-is, not rewritten)

**Sprint intent:** FU-38's mid-entry `**Status:** OPEN. Resolution BBF:` declaration is retired. The
entry's canonical lead already says RESOLVED (PR #140); what remained open was the entry's own
residual scope — 2 full-history gitleaks findings whose content lives in two deleted
`CHESS COACH _*.md` files. A product-owner scope decision on 2026-10-27 accepts those 2 as
residual risk instead of discharging them with a destructive history rewrite. This flip records
that decision in the ledger, adds a `## Resolved` entry, and corrects two factual errors the
entry's lead block carried.

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified,
`docs/16_audit/BBF-doc-drift-flip-13.md` NEW per-flip brief).

**Base:** `main @ 7848c51e535831c8dedc51048df5e160a21df8ae` (PR #182 merge commit, the squash of
the FU-47 orphan `.bak` deletion).

**Sibling flips:** flip-10 (FU-21, PR #176), flip-12 (11 stale statuses, PR #177). flip-11 was
never published — no commit, no branch, and no brief exist for it on `origin/main`, so this is
flip-13 rather than flip-11.

---

## §1. Why this flip exists

`docs/16_audit/OPEN-FOLLOWUPS.md` holds FU-38 at lines 2782-2911 after this flip (2782-2887
before it). Reading that entry in order, the pre-patch structure was:

| Pre-patch line (on the base tree `7848c51e`) | Content |
|---|---|
| L2782 | `## FU-38 — 29 pre-existing historical gitleaks findings (allowlist fix)` |
| L2784 | `**Status:** **RESOLVED 2026-10-15 via squash-merge of PR #140**` — the canonical lead |
| L2855 | `**Status:** OPEN. Resolution BBF:` — **stale** |
| L2856 | the resolution-BBF pointer to `docs/16_audit/BBF-FU-38-pre-existing-leaks.md` |
| L2858 | `**Out of scope:**` |
| L2860-2865 | the 2 deleted-file findings, "Tracked as a future BBF" — the residual scope |
| L2870-2873 | the `security-audit.yml` Node-20 pins, "Tracked as a future BBF (FU-41 candidate)" |

flip-12 deliberately left this line alone. Its PR body classifies FU-38 as `LIVE OPEN` and says
so explicitly: "The allowlist resolves 27/27 in-scope findings, but the entry explicitly retains 2
deleted-file full-history findings as residual scope". Its brief says the same thing more
tersely: "external triage category: `LIVE OPEN`, because two deleted-file findings remain
residual scope". That classification was correct against the ledger as it stood. What changed is
the product owner's decision, not the tree.

**The scope gate.** Per `docs/16_audit/BBF-FLIP-PROCESS-RULES.md` §6, an entry's status is decided
by walking its own enumerated scope step by step. FU-38's enumerated scope has two steps:
(a) the allowlist fix — discharged by PR #140; (b) the 2 deleted-file findings — named by the
entry itself as residual scope, with two named remedies (git-filter-repo history rewrite, or a
permanent allowlist entry for the deleted-file SHAs). Step (b) was not discharged by any commit.
A flip that deleted step (b) from the record would have destroyed live scope.

**The product-owner decision (2026-10-27) resolves step (b) by accepting it, not by discharging
it.** The two findings are real (see §3), but they are historical artifacts of a local
development host: a per-restart gateway session token, captured in a diagnostic report, from a
gateway that no longer exists. The decision is to accept them as residual risk and close the
entry — explicitly *accepted as-is, not rewritten* — rather than rewrite history or add an
allowlist entry for the two blob SHAs.

---

## §2. The replacement

Pre-patch line 2855 (on the base tree `7848c51e`):

```
**Status:** OPEN. Resolution BBF:
```

Post-patch line 2879 (on the final head):

```
**Status:** RESOLVED 2026-10-27 via product-owner scope decision (accepted as-is, not rewritten); see the canonical resolution above and the `## Resolved` entry below. Historical resolution-BBF pointer preserved below:
```

**Shape: A′ — replace the stale mid-entry block.** The entry already leads with a correct
RESOLVED status, and the stale declaration sits mid-entry, so this is the flip-9b / flip-9c shape
rather than a prepend. The resolution-BBF pointer on the following line is preserved verbatim
(1-for-1 line replacement), and the trailing clause marks it as historical so a reader landing
on it does not mistake it for live scope.

Two further edits inside the same entry, each 1-for-1 or near-neutral:

- L2865 on the base tree (`Tracked as a future BBF.` → `Accepted as-is, not rewritten.`): the
  residual scope is now disposed rather than pending.
- L2872-2873 on the base tree (the Node-20 pins bullet no longer says "Tracked as a future BBF
  (FU-41 candidate)"; FU-41 shipped, merge `cab74655`, so the bullet now says so).

And two additive blocks, inserted after the canonical lead:

- A `**Status (clarified 2026-10-27, doc-drift flip-13):**` block declaring the live status.
- A `**Correction (2026-10-27, doc-drift flip-13)**` block recording the two factual errors in
  the lead (see §4). The lead block is preserved byte-identically — the correction sits beside
  it, in the correction convention already used by FU-45 / FU-46 in this same merge series.

All line numbers in §1 and §2 above are stated on the base tree unless a tree is named
explicitly. The post-patch equivalents, measured on the final head, are: the canonical lead at
L2784; the clarification block at L2798; the correction block at L2806; the retired status
declaration at L2879; the `## Resolved` section heading at L3349; the new FU-38 `## Resolved`
entry at L3444; the FU-38 entry's full extent at L2782-L2911.

---

## §3. The measured basis for accepting the 2 findings

Everything in this section was measured in this session against a fresh clone of `origin/main`,
not quoted from the ledger.

The clone has 447 commits on `main` and 476 reachable across all refs (44 of the `main`
commits are merges). gitleaks reported "430 commits scanned" for the full-history scan; that
figure is gitleaks' own count of the commits it walked, and it is reported here as measured
rather than derived — the scan was run against all refs, not only `main`.

Three full-history scans, gitleaks 8.24.2 (the version the CI action bundles):

| Config | Corpus | Findings |
|---|---|---|
| `.gitleaks.toml` as it stood at `3f056c6f` (the PR #140 parent) | through `3f056c6f` | 29 |
| merged `.gitleaks.toml` with the `[allowlist]` block removed | through `3f056c6f` | 31 |
| merged `.gitleaks.toml` as-is | through `3f056c6f` | 2 |
| merged `.gitleaks.toml` as-is | through `origin/main` | 2 |

The 31-vs-29 difference is the two `tests/unit/test_log_redaction.py` fixtures, which the
allowlist already present at `3f056c6f` covered and which were added by commit `d15bb306`
(2026-10-15) — after the ledger's 29-finding baseline was taken. The 2 findings that survive
every configuration are the same 2: one `generic-api-key` hit in
`CHESS COACH _ Diagnostic Report for External Review.md`, one in
`CHESS COACH _ Claude Review_ Definitively Fixing _Backend Not Found_ and _Analysis Error.md`.

**Provenance of the 2 findings.** Both files were added by commit `44a9a3e3` (2026-05-18,
author "Agent Zero") and deleted by commit `fa77660b` (PR #52, 2026-07-31). `44a9a3e3` is an
ancestor of `cd43906c` and of `main`; both commits are ancestors of `origin/main`. Each file is a
captured gateway diagnostic report containing a literal `session_token` value.

**Why the values are inert.** Each is 43 characters of urlsafe-base64 — exactly the format of
`generate_token()` in `services/chess_coach/gateway/descriptor.py`, which calls
`secrets.token_urlsafe`. `generate_token_if_needed()` in `services/chess_coach/gateway/auth.py`
returns a fresh token on every gateway restart unless `CHESS_COACH_BACKEND_TOKEN` is set as a
static token. Neither value appears anywhere in the current tree (`git grep` for both prefixes
returns nothing); they exist only in history, and the gateway they authenticated to is gone.

**Why no allowlist entry was added.** The allowlist is path-based and rule-scoped. Adding an
entry for the two blob SHAs would suppress the finding *class* rather than the instance, and
would keep a real secret of the same shape invisible at that path forever. Leaving them
unlisted keeps a real secret at a new path flagged. That is the correct posture for a
secret scanner, and it is why "accepted as-is" is the right disposition.

**What was deliberately not done.** No `git-filter-repo` history rewrite — it rewrites every
descendant SHA and is destructive to the published history. The two `shift+arrow*` matches in
`apps/desktop/src/state/keybinds.ts` were left in place; they are keyboard-binding strings
inside a TypeScript object literal, and removing them is a refactor rather than a security fix.

---

## §4. Two factual corrections to the lead block

The canonical lead block is preserved byte-identically. The corrections are recorded in an
adjacent `**Correction (2026-10-27, doc-drift flip-13)**` block, following the correction
convention already used by FU-45 and FU-46.

**Correction 1 — the introduction commit.** The lead's `**Identified:**` paragraph says the 2
deleted-file findings were "introduced in `cd43906c`, deleted by `fa77660b`". Measured against a
full clone: `git log --diff-filter=A` reports both files as ADDED in `44a9a3e3` (2026-05-18).
`cd43906c` (2026-07-13) is a later commit that merely still contained the files. The correction
block names `44a9a3e3` as the introduction commit and states the `cd43906c` relationship.

**Correction 2 — the CI attribution.** The lead says "12/12 CI green on `cab74655`". Measured:
`cab74655` is the PR #141 merge commit (`Merge pull request #141 from
sebko23/bbf-fu-41-security-audit-yml-node20`), which is a different PR from #140. The 12 green
check-runs belong to `d78b9b9b` and to the PR #140 merge commit `1dbf59e8` — 12 check-runs, all
`completed`/`success`, on each of the two SHAs, confirmed via the GitHub check-runs API.

**Third, forward-looking finding — not a correction to the lead, but a new measurement.** The
merged `.gitleaks.toml` names `lichess-pat` in `targetRules`. gitleaks 8.30.1 refuses to load
that config: `[[allowlists]] target rule ID 'lichess-pat' does not exist`. CI is green only
because `gitleaks-action@v3` bundles gitleaks 8.24.3, where the config loads. Dropping
`lichess-pat` from `targetRules` was measured to restore the identical 2-finding result on 8.30.1
(the rule id is defensive — the log-redaction fixtures match `generic-api-key`, not `lichess-pat`),
so the fix is one line. That is a config change to a live CI-adjacent file and is therefore
tracked as a separate BBF, not discharged by this doc-only flip. The ledger's `## Resolved` entry
records the finding so it is not lost.

---

## §5. The `## Resolved` entry

Added at the end of the `## Resolved` section, following the section's existing convention (one
`### FU-NN — RESOLVED, ...` heading, an `**Original entry:**` line-range pointer, and a
`**Resolution:**` line). The range pointer cites the post-edit range 2782-2911.

---

## §6. Explicit exclusions

This flip does not touch:

- **FU-20** at L1664 — untouched. Its `**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:` line is byte-identical to the base.
- **FU-35** at L2538 — untouched. Its `**Status:** OPEN. Resolution shape:` line is byte-identical to the base.
- **L1786** — historical prose inside FU-21's preserved block, untouched.
- Any source file, test, lockfile, package manifest, workflow, or `.gitleaks.toml`.
- The `lichess-pat` `targetRules` entry — measured, documented, and deliberately deferred to a separate config BBF.
- The two `shift+arrow*` matches in `keybinds.ts` — a refactor, not a security fix.

---

## §7. Verification performed on the pinned head

- Exactly 4 ledger lines are removed from the base and 87 added; a full line-by-line diff of the two blobs shows no other changed line.
- The `## FU-38` heading, the canonical lead block, the 27-findings table, the "Why these are false positives" block and the "The fix" block are byte-identical to base.
- Every cited SHA exists and is an ancestor of the base: `d78b9b9b`, `1dbf59e8`, `3f056c6f`, `44a9a3e3`, `fa77660b`, `cd43906c`, `d15bb306`, `cab74655`.
- `git diff --check` clean.
- `scripts/dev/verify_commit_refs.py` passes against the final commit body.
- `scripts/dev/verify_bbf_flip_rules.py` manifest mode passes against the final head.

---

## §8. Provenance

Authored and verified on this host against the canonical remote `origin/main`. All gitleaks
measurements were taken in a scratch clone outside the repository working tree, so no scan
artifact was committed and the repository's untracked baseline is untouched.
