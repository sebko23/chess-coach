# BBF-doc-drift-flip-10 — flip FU-21's stale mid-entry `Status: OPEN` line in OPEN-FOLLOWUPS.md

**Sprint intent:** FU-21's entry carried a stale `**Status:** OPEN. Real contract gap.` line
positioned *above* its own two clarification blocks, the later of which declares the entry
RESOLVED. This flip retires the stale status line and points it at the clarification that is
already the canonical LIVE marker.

**This is the 10th doc-drift flip.** Sibling flips: flip-9a (FU-15 headline, PR #172),
flip-9b (FU-17 mid-entry `OPEN` block, PR #173), flip-9c (FU-19 + FU-42 statuses, PR #174).

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified,
`docs/16_audit/BBF-doc-drift-flip-10.md` NEW per-flip brief).

**Base:** `main @ 42e426cc776ae9215d42d1972c81bd8bc97cfc6f` (PR #175 merge commit, the
squash of the FU-20 network-skip correction).

---

## §1. Why this flip exists

`docs/16_audit/OPEN-FOLLOWUPS.md` holds FU-21 at lines 1702–1819. Reading that entry in
order:

| Line (pre-patch) | Content |
|---|---|
| L1722 | `**Status:** OPEN. Real contract gap. Investigation-first BBF would:` — **stale** |
| L1723–1726 | the 4-line investigation plan (chroot / AppLocker / sandboxed-profile) |
| L1728 | `**Status (clarified 2026-10-18, doc-drift flip-6):** PARTIALLY RESOLVED ...` |
| L1750 | `**Status (clarified 2026-10-19, doc-drift flip-7):** **RESOLVED 2026-10-19** ...` |

The entry's own live status is RESOLVED as of flip-7 (PR #170), with the implementation
landing in PR #169 (`d3fbb35c`, BBF-FU-21-bind-mount). Yet the first `Status` line a reader
or `grep` encounters still says OPEN.

This is the same defect class as flip-9b (FU-17) and flip-9c (FU-19): a stale status line
that survives because a later block corrected the conclusion without retiring the earlier
claim. `grep "Status: OPEN"` still matches here.

**FU-20 is NOT clean, and this flip does not fix it.** Its entry leads with
`PARTIALLY RESOLVED 2026-10-18` (L1637) but still carries a stale
`**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:` at **L1664**, below
its own lead, with a pre-#163/#164 investigation plan. It is structurally the same defect
this flip repairs. It went undetected because its wording differs from the FU-21/FU-22
string, so an exact-string grep for the FU-21 line does not match it. FU-20 therefore needs
its own flip (flip-11 or later); see §4.

---

## §2. The replacement

Pre-patch line 1722:

```
**Status:** OPEN. Real contract gap. Investigation-first BBF would:
```

Post-patch line 1722:

```
**Status:** RESOLVED 2026-10-19 via PR #169 (`d3fbb35c`, BBF-FU-21-bind-mount); see the flip-7 clarification below. Historical investigation plan preserved below.
```

**Shape: minimal, matching flip-9c's FU-19 treatment rather than flip-9b's.** The
investigation plan beneath it is retained verbatim. Deleting it would remove the record of
*how* the gap was to be closed, and the trailing clause marks it as historical so a reader
landing on the plan does not mistake it for a live TODO.

Ledger delta: `-1 / +1` (one line replaced; the ledger stays at 3139 lines, verified
against `main @ 42e426cc`).

---

## §3. Preserved byte-identical

Verified by direct diff against `main @ 42e426cc`:

- FU-21 heading (L1702) and the `Identified:` / `Per ... §A-F11 property 3` preamble (L1704–L1721)
- the 4-line investigation plan (L1723–1726) — retained verbatim, not deleted
- the flip-6 clarification block (L1728–L1748) — `PARTIALLY RESOLVED 2026-10-18`
- the flip-7 clarification block (L1750 onward) — `RESOLVED 2026-10-19`, the canonical LIVE marker
- everything from L1820 on, including **FU-22** — which carries an *identical* stale
  `**Status:** OPEN. Real contract gap. Investigation-first BBF would:` line at L1860 and is
  **deliberately out of scope for this flip** (see §4)

---

## §4. What this flip does NOT do

- **Does not touch FU-22.** Its L1860 line is byte-identical to the string replaced in
  FU-21, which is why this flip's edit required leading context to disambiguate. FU-22 is the
  2 GB memory-cap entry and has its own separate status history; correcting it is a distinct
  BBF, not a drive-by edit inside flip-10.
- **Does not touch FU-20**, which has the same defect class at L1664 (see §1). Correcting
  it is a separate flip. A ledger-wide `**Status:** OPEN` sweep is warranted before the next
  flip is scoped, because this flip's disambiguation grep was anchored to one exact string
  rather than to the class of line.
- **Does not edit either clarification block.** Both are preserved byte-identical; flip-10
  only retires the stale headline above them.
- **Does not delete the investigation plan.**
- **Does not re-implement FU-21.** Its bind-mount implementation is on `main` via PR #169.
- **Does not touch any file outside `docs/16_audit/`.**

---

## §5. Verification (live, this session)

- Base confirmed before branching: `git rev-parse main` → `42e426cc`; tracked working tree
  clean; branch `bbf-doc-drift-flip-10` did not previously exist.
- **Edit disambiguation:** `patch` initially reported **2 matches** for the target string
  (FU-21 L1722 and FU-22 L1860). Resolved by supplying the preceding A-F11 line as context so
  only FU-21 was rewritten. Verified FU-22's line is untouched in the post-patch diff.
- Diff shape: single 1-line replacement, `1 1` on the ledger.
- Anchor semantics checked post-patch: the new L1722 contains the FU-21 status; the plan at
  L1723–L1726 is unchanged; both clarification headers still resolve at their original lines
  (the edit is line-count-neutral, so no anchors shift).

Pre-commit hygiene:

- Fresh branch from `main @ 42e426cc`, zero prior commits at branch creation.
- Author and Committer forced to `Sebastian Wasielewski <lesson@o2.pl>`.
- No force operations expected; push should be an ordinary `git push -u` for a new branch.

---

## §6. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-21 region: stale status at L1722 (the target), investigation plan L1723–L1726, flip-6 clarification L1728–L1748, flip-7 clarification L1750+ (the canonical LIVE marker).
- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-22 region: identical stale string at L1860 — out of scope, see §4.
- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-20 region: leads with `PARTIALLY RESOLVED 2026-10-18` at L1637 but also carries a stale `**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:` line at L1664; it needs a separate flip and is out of scope for flip-10.
- `docs/16_audit/BBF-doc-drift-flip-9b.md` (flip-9b, PR #173) — structural precedent for retiring a mid-entry `Status: OPEN` block.
- `docs/16_audit/BBF-doc-drift-flip-9c.md` (flip-9c, PR #174) — precedent for retaining an investigation plan under a corrected status line.
- PR #169, squash `d3fbb35c` (BBF-FU-21-bind-mount) — the implementation this flip's status line cites.
- PR #170, squash `c883c352` (flip-7) — the flip that established the RESOLVED status.
- PR #175, squash `42e426cc` — this flip's base.

---

## §7. Pre-leaf-review checklist

1. **Numstat:** read `git diff --numstat main..HEAD` live; the ledger must show `1 1` and the
   brief its own measured count. Do not assume.
2. **FU-22 untouched:** confirm the diff contains exactly one hunk and that FU-22's L1860
   `Status: OPEN` line is byte-identical to `main`.
3. **Plan preserved:** FU-21's 4-line investigation plan must be unchanged.
4. **Clarifications preserved:** both the flip-6 and flip-7 blocks byte-identical.
5. **No stale figures:** grep the brief for any `L####` anchor and resolve each against the
   committed ledger — the brief asserts specific line numbers, and those must be true.
6. **Identity:** Author and Committer both `Sebastian Wasielewski <lesson@o2.pl>`.
7. **Scope:** exactly 2 files, both under `docs/16_audit/`.