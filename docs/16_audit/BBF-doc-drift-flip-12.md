# BBF-doc-drift-flip-12 — retire 11 stale mid-entry `Status: OPEN` declarations in OPEN-FOLLOWUPS.md

**Sprint intent:** Retire 11 stale mid-entry `**Status:** OPEN` declarations whose own entries
already lead with a verified RESOLVED marker. Each replacement points to that canonical marker.
Substantive historical context remains below the pointer; no implementation work is included.

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified,
`docs/16_audit/BBF-doc-drift-flip-12.md` NEW per-flip brief).

**Base:** `main @ 1aa3808b7aa427bd902b5fcd0abfcee0de55f745`.

---

## §1. Why this flip exists

The ledger contains 11 stale mid-entry OPEN declarations after independently verified fixes
had already shipped. Each target sits in an entry whose canonical lead says RESOLVED. The
decisive test applied was scope discharge: verify every step of the entry's own enumerated
scope against the live tree and history, not merely whether the named subject exists.

| Pre/post ledger line | FU | Scope discharged | Canonical resolution |
|---:|---:|---|---|
| 565 | FU-8 | dead narration-context plumbing | commit `aee6038e` |
| 763 | FU-10 | `h2 >= 4.4.1` CVE pin | commit `2a6276bd` (PR #83) |
| 894 | FU-12 | 7 pnpm workspace overrides | commit `74cab77b` (PR #123) |
| 1298 | FU-16 | 3 ProfileDashboard async-data tests | merge commit `77a83796` (PR #89) |
| 1860 | FU-22 | 4-step 2 GiB memory-cap plan | merge commit `ae543ea8` (PR #145) |
| 2317 | FU-31 | glob-convention meta-test rewrite | commit `042f56c1` |
| 2372 | FU-32 | route `os.path.isdir()` pre-check | commit `b4a8e5f0` |
| 2420 | FU-33 | accepted stale commit-body reference | commit `fd984efd` |
| 2645 | FU-39 | gitleaks action v2 -> v3 | merge commit `47062dfa` (PR #138) |
| 2740 | FU-40 | smoke workflow action-pin sweep | commit `8f79469c` (PR #139) |
| 2944 | FU-41 | security workflow action-pin sweep | commit `660e1172` (PR #141) |

Each edit is a one-line-for-one-line replacement. Because the replacement is line-count
neutral, pre/post ledger anchors are identical.

---

## §2. Replacement shape

For each target, the stale OPEN declaration's first line becomes a compact RESOLVED pointer to
the canonical lead in the same entry. Where historical prose follows, the pointer explicitly
labels it historical and the continuation lines remain byte-identical. FU-31, FU-32, FU-39,
FU-40, and FU-41 had one-line stale declarations and now have one-line resolved pointers.

Examples:

```text
**Status:** RESOLVED 2026-10-16 via merge commit PR #145 (`ae543ea8`); see the canonical resolution above. Historical investigation plan preserved below:
```

```text
**Status:** RESOLVED 2026-08-27 via commit `b4a8e5f0`; see the canonical resolution above.
```

---

## §3. Explicit exclusions

This flip does not touch:

- **FU-20** at L1664 — ledger text remains `**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:`; external triage category: `NEEDS EVIDENCE`, pending the Windows Job Object scope decision.
- **L1786** — historical prose, not a declaration record.
- **FU-35** at L2538 — ledger text remains `**Status:** OPEN. Resolution shape:`; external triage category: `LIVE OPEN`, because the runtime hook and tree-level spec scope remain.
- **FU-38** at L2855 — ledger text remains `**Status:** OPEN. Resolution BBF:`; external triage category: `LIVE OPEN`, because two deleted-file findings remain residual scope.
- Any source, lockfile, package manifest, workflow, or unrelated ledger text.

The excluded anchors were compared byte-for-byte with the base tree and are identical.

---

## §4. Verification

Live checks on the branch worktree:

- Git numstat: `11 11 docs/16_audit/OPEN-FOLLOWUPS.md`.
- Diff hunks: exactly 11, one at each ledger line listed in §1.
- `git diff --check`: clean.
- Ledger line count: unchanged from the base tree.
- Every target anchor resolves to its expected RESOLVED pointer.
- FU-20, L1786, FU-35, and FU-38 anchors are byte-identical to the base.
- Every SHA used by the 11 pointers resolves to an ancestor of the base.
- Topology terminology matches the verified parent counts: FU-16, FU-22, and FU-39 point
  to two-parent merge commits; FU-8, FU-10, FU-12, FU-31, FU-32, FU-33, FU-40,
  and FU-41 point to single-parent commits.
- The 11 pointer SHAs are distinct from the disclosed legacy SHA: FU-39's older
  canonical lead also names source SHA `bd49dd1c`, which is not present in the local object
  database. The pointer therefore cites the locally verified merge commit `47062dfa` and
  does not repeat the unresolved source SHA.

---

## §5. Pre-push checklist

1. Re-run the full verification sweep against the committed head.
2. Confirm exactly two tracked files differ from the base.
3. Confirm the ledger remains `11/11` and has exactly 11 status-line hunks.
4. Confirm all §1 anchors resolve semantically to the stated RESOLVED pointer.
5. Confirm excluded anchors and unrelated text are byte-identical.
6. Confirm all cited SHAs exist, are ancestors, and have the stated topology.
7. Pin the immutable commit SHA before independent review.
