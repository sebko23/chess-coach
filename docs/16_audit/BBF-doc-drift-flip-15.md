# BBF-doc-drift-flip-15 — correct FU-2's stale status declaration

**Sprint intent:** FU-2's plain `**Status:**` declaration still says
`PARTIALLY RESOLVED` because its option (a), UCI-to-SAN conversion, was
tracked separately as FU-5. FU-5's implementation shipped on 2026-08-06,
and PR #196 later corrected FU-5's canonical ledger declaration. FU-2's own
three-option scope is therefore now discharged, but its headline still
reports the former partial state. This flip replaces that one stale line
without changing the ledger's line count or any historical prose.

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified,
`docs/16_audit/BBF-doc-drift-flip-15.md` NEW per-flip brief).

**Base:** `main @ 78c804c331d8c051bef4d59b3b2470350730d02d` (the PR #196
squash merge).

**Sibling flips:** flip-12 retired 11 stale FU statuses, flip-13 closed
FU-38, and flip-14 corrected FU-5's and FU-6's stale declarations. This flip
addresses FU-2's distinct one-line status shape.

---

## §1. Why this flip exists

FU-2 originally enumerated three mutually related alternatives:

- option (a): add UCI-to-SAN conversion in the narration route or pipeline;
- option (b): correct the `pv_moves` schema docstring from SAN to UCI; and
- option (c): convert engine PV to SAN at the route boundary and expose both
  fields.

The original doc-fix BBF shipped option (b) on 2026-08-04 in squash
`3cf012b8` (PR #79). It deliberately deferred option (a) to FU-5, so the
ledger correctly recorded FU-2 as `PARTIALLY RESOLVED` at that time.

FU-5 later shipped the additive `pv_moves_san` behavior on 2026-08-06 in
squash `cada4ab2` (PR #81). The current tree contains `_pv_to_san()`, the
narration route's `pv_moves_san` response field, the protocol type's
`pv_moves_san` field, the frontend's `pv_moves_san ?? pv_moves` fallback,
and the regenerated desktop API type. PR #196 (`78c804c3`) did not implement
FU-5; it corrected FU-5's canonical ledger declaration so that FU-5 reads
as RESOLVED.

That PR did not make FU-2 stale; flip-8 had already identified FU-2's
partial wording as technically stale once FU-5 was resolved. FU-2 still
says its option (a) is tracked separately as FU-5 even though that separate
item is now resolved. This flip corrects FU-2's own status without
rewriting its issue history.

---

## §2. The scope-discharge test (docs/16_audit/BBF-FLIP-PROCESS-RULES.md §6)

Per §6, the entry's status is decided by walking its own enumerated scope:

- option (b) is discharged by `3cf012b8`, which corrected the protocol and
  pipeline docstrings to describe UCI accurately;
- option (a) is discharged by FU-5's `cada4ab2`, which shipped the
  human-display SAN translation while keeping UCI authoritative; and
- option (c) is superseded by the additive FU-5 design rather than an open
  third implementation obligation.

There is no undischarged step in FU-2's enumerated scope. The three cited
SHAs exist and are ancestors of the pinned base. The current tree's
`_pv_to_san()` implementation and frontend fallback independently confirm
that option (a) is present rather than merely named in the ledger.

---

## §3. The replacement shape

FU-2 has one plain `**Status:**` line and no `**Status (clarified ...)**`
block. The correct shape is therefore the flip-12 one-line-for-one-line
replacement, not the flip-14 pointer-to-clarified-block shape:

```text
**Status:** **RESOLVED 2026-08-06** by the original doc-fix BBF (`3cf012b8`, PR #79) and FU-5 (`cada4ab2`, PR #81); FU-5's canonical ledger status was corrected by PR #196 (`78c804c3`). Historical context preserved below:
```

Only that line changes. The preceding option list and the following line
that says option (a) was tracked as FU-5 remain byte-identical historical
context. The new declaration explicitly identifies the later line as
history, so the old deferral wording is preserved without continuing to
read as the current status.

---

## §4. Line-count neutrality is load-bearing here

PR #194 landed ten `**Original entry:** lines N-M` pointers in this same
ledger. Their values are line numbers, and every target sits below this
flip's edit region. Any net line-count change would shift those pointers
and reintroduce the stale-pointer defect PR #194 was merged to fix.

This flip replaces one ledger line with one ledger line. The ledger stays
3,884 lines with a trailing newline, and every non-L56 ledger line remains
byte-identical to the base tree. All ten pointer values and their Rule-B
resolution remain unchanged.

---

## §5. Scope and maintenance cost

**Changed files:** exactly two:

- `docs/16_audit/OPEN-FOLLOWUPS.md`: one insertion and one deletion;
- `docs/16_audit/BBF-doc-drift-flip-15.md`: this new per-flip brief.

**Recurring maintenance cost:** negligible. No source, test, generated API,
workflow, or configuration changes are required. The corrected ledger line
cites existing implementation SHAs and requires no runtime dependency.

**Runtime verification limitation:** the canonical `uv run pytest` focused
command exceeded its bounded timeout while creating the project environment
and downloading dependencies. A second attempt using preinstalled packages
could not resolve this worktree's project package: the smoke import failed
(`ModuleNotFoundError: chess_coach.narration`), and another environment
resolved a different Chess Coach tree. These are environment/bootstrap
failures, not observed test failures; no passing runtime result is claimed
here. Repository checks remain the acceptance gates for this
documentation-only change.

---

## §6. Explicit exclusions

This flip does not touch:

- FU-3, FU-4, or any other FU entry;
- the BBF-86.7 corpus-versioning work or PR #48;
- the false `shipped` claims in the BBF-86 audit briefs;
- FU-5's implementation or ledger entry beyond the historical PR #196
  reference in FU-2's replacement line;
- any source, test, workflow, configuration, lockfile, or generated API file.

BBF-86.7 is a separate defect class. Commit `f0253b0` is not an ancestor of
main, so whether to land or reconstruct that work and how to correct the
related audit prose require a separate BBF and decision. They are not
bundled into this narrow FU-2 status correction.

---

## §7. Honest limitations

- This flip changes no behaviour and closes no functional gap. Both the
  schema correction and FU-5's conversion behavior had already shipped.
- The corrected declaration records when the combined enumerated scope was
  discharged (2026-08-06), while PR #196 is cited only for its later
  ledger-status correction.
- The runtime-test environment did not yield a bounded local result; CI and
  reviewers should still apply the repository's normal test expectations.
