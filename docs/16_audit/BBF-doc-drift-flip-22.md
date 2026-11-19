# BBF-doc-drift-flip-22 — correct fifteen stale current-state claims in earlier flip briefs

**Date:** 2026-11-19
**Type:** documentation maintenance (prose only, no behavioural surface)
**Base commit:** `9b02ae5ac56ec958e258a01518ef67738edb219f`
**Corrects:** fifteen stale current-state claims in thirteen earlier per-flip
briefs — the claim in two of them that BBF-86.7's corpus-versioning scope was
unlanded and that the BBF-86 audit briefs' `shipped` claims were false, and
thirteen further claims that named FUs or a config rule as still open after
they had been resolved

## §1. What this BBF does

Thirteen earlier per-flip briefs carry a current-state claim that a later
landing made false. In every case the claim was **true when written** and is
**stale now**, and in every case it is a *present-tense* statement about a
scope, an FU status, or a merged config — not a historical record. One of the
fifteen passages is an over-statement that was imprecise when written; see §3.4.

This BBF corrects those fifteen passages in place, preserving each original claim
as the dated historical reading and adding an inline
`**Correction (2026-11-19, doc-drift fix-up):**` block that states the live
status. Nothing is deleted; the historical readings stay readable. The scope
decision each original flip made is not re-opened — only its current-state
claim is corrected.

## §2. Why the BBF-86.7 passages became stale

Both briefs landed on 2026-11-13. PR #199 (`0243d315`) — the reviewed BBF-86.7
implementation — landed on **2026-11-14**, the day after. It is an ancestor of
`main`.

| Claim in the briefs | True on 2026-11-13 | Live on `main` now |
|---|---|---|
| The two audit briefs claim BBF-86.7 is `✅ shipped`, citing PR #48's commit | yes | **no** — both read `Implemented by this BBF`; the release-readiness brief adds `PR #48 is historical` |
| The corpus `version` field is absent from the base tree | yes | **no** — present as `_metadata.version` in `tests/gold/narrative/v2/corpus.json` |
| The Dockerfile `BUILD_ARG` flags are absent from the base tree | yes | **no** — `NARRATIVE_VERSION=v2`, `ARCHETYPE_VERSION=v0` are present |
| BBF-86.7's scope is unlanded / not discharged | yes | **no** — discharged by PR #199 |

The briefs therefore carried a quotation that no longer resolves against either
document, and an "unlanded" verdict for work that had landed.

## §3. The fifteen passages, and what each becomes

### §3.1 `BBF-doc-drift-flip-16.md` §6

The passage claimed the two audit briefs "both claim BBF-86.7 is `✅ shipped`",
that PR #48's commit was not an ancestor of the base, and that the corpus
`version` field and Dockerfile `BUILD_ARG` flags "are absent from the base
tree". The passage is now framed as the 2026-11-13 reading, followed by a
correction block that records: PR #199 shipped the scope on 2026-11-14; the
`version` field and the `BUILD_ARG` flags are now in the tree; the two audit
briefs no longer claim `✅ shipped`; and PR #48 was closed as superseded on
2026-11-19, so the quoted wording no longer resolves.

### §3.2 `BBF-doc-drift-flip-15.md` §6

The passage excluded "the false `shipped` claims in the BBF-86 audit briefs"
and said that commit `f0253b0` not being an ancestor of `main` meant whether to
land or reconstruct the work "require[d] a separate BBF and decision". The
exclusion bullet now records that the claims read as false when the flip was
written and were corrected separately on 2026-11-14, and the paragraph now
carries a correction block recording that PR #199 shipped the reviewed
implementation, that the `version` field and `BUILD_ARG` flags are now in the
tree, and that BBF-86.7's scope is discharged by PR #199.

One sub-claim is **deliberately left standing**: commit `f0253b0` is still not
an ancestor of `main`. The work landed through a *different* reviewed commit
(`0243d315`), so the original commit's non-ancestry remains true and is stated
as such rather than smoothed over.

### §3.3 The thirteen passages the first sweeps missed

Each of these thirteen is the same shape: a present-tense claim, in a per-flip
brief, that a named FU or a merged config was still open at the time the brief
was written and has since been resolved. One of them — flip-8's FU-15 — is
recorded as an imprecision rather than a drift, because it was already
over-stated when written; see §3.4.

| Brief | Claim | Resolution |
|---|---|---|
| `BBF-doc-drift-flip.md` | the 13-FU exclusion table's "genuinely still OPEN" framing | 10 of 13 rows now name resolved FUs; FU-9, FU-23, FU-27 remain OPEN |
| `BBF-doc-drift-flip-3.md` | the "8 still-open FUs" list | FU-5, FU-6, FU-11, FU-21 resolved; FU-9, FU-23, FU-27 remain OPEN |
| `BBF-doc-drift-flip-4.md` | the "7 still-open FUs" list | FU-5, FU-6, FU-11, FU-21 resolved; FU-9, FU-23, FU-27 remain OPEN |
| `BBF-doc-drift-flip-7.md` | FU-11β listed among "genuinely unimplemented work" | FU-11 resolved for the approved α-ext scope on 2026-11-04 |
| `BBF-doc-drift-flip-8.md` | FU-15 and FU-42 "still OPEN per the headline" | FU-15 FULLY RESOLVED; FU-42 RESOLVED via PR #143 |
| `BBF-doc-drift-flip-12.md` | three "external triage category" assertions | all three entries are now RESOLVED |
| `BBF-doc-drift-flip-13.md` | the merged `.gitleaks.toml` names `lichess-pat` | PR #184 removed that id the same day, after this brief landed |
| `BBF-doc-drift-flip-13.md` | its §6 exclusion bullets: FU-20's and FU-35's mid-entry `**Status:** OPEN` lines | FU-20's lead is superseded; FU-35's quoted line is gone |
| `BBF-doc-drift-flip-9c.md` | FU-20's "status reads `PARTIALLY RESOLVED 2026-10-18`" | FU-20 is RESOLVED for the named release scope |
| `BBF-doc-drift-flip-8.md` | FU-2's "PARTIALLY RESOLVED" shape | FU-2 is RESOLVED; its deferred part was discharged by FU-5 |
| `BBF-doc-drift-flip-9a.md` | FU-2's "PARTIALLY RESOLVED" shape (the same bullet) | the same |
| `BBF-doc-drift-flip-14.md` | FU-2's "PARTIALLY RESOLVED" shape | the same |
| `BBF-doc-drift-flip-10.md` | FU-20's entry "leads with `PARTIALLY RESOLVED 2026-10-18`" | FU-20 now leads with `RESOLVED for the named release scope` |

Each receives one inline `**Correction (2026-11-19, doc-drift fix-up):**` block
in the same house shape as the two BBF-86.7 corrections: the original claim is
preserved as the dated reading, and the block states the live status and names
the resolution. In every case the correction states that the original scope
decision was correct when made and is not re-opened.

### §3.4 One correction that inherited an over-statement

flip-8's bullet says of FU-15 and FU-42: "Both are still OPEN per the
headline". For FU-42 that was true at flip-8's base. For FU-15 it was not:
FU-15's own `**Status:**` line read `PARTIAL` there, and it was flipped to
RESOLVED by flip-9a later the same day. So the bullet was an *imprecise*
claim for FU-15, not a claim a later landing overturned. The correction block
now says exactly that, instead of folding FU-15 into the "a later measurement
established it" framing, which would have been false. This is the difference
between a stale claim and an over-stated one, and the correction records which
one it is.

## §4. What is NOT edited

- **The ledger** `docs/16_audit/OPEN-FOLLOWUPS.md` — not touched. Its geometry and
  all ten PR #194 `Original entry` pointer values are therefore unaffected, and
  no pointer arithmetic is needed.
- **The two BBF-86 audit briefs** — `BBF-86-release-readiness-audit.md` and
  `EXTERNAL-REVIEW-FINDINGS-2026-07-28.md`. Their BBF-86.7 wording is already
  correct (`Implemented by this BBF`), so they need no change.
- **`BBF-86.7-corpus-versioning.md`** — the landed BBF-86.7 brief already
  records PR #48 as historical and the landed implementation as current.
- **The original wording of either passage** — preserved in place, dated to
  2026-11-13, and marked as the historical reading.
- **Every other flip brief** — swept for the same class of claim. The first
  two sweeps each missed further sites, and later reviews found more; see §5
  and §5.1 for how the sweep was widened and what it found. All thirteen are
  corrected here too.
- **Four non-flip briefs in `docs/16_audit/`** — `BBF-FU-20-impl-windows.md`,
  `BBF-FU-21-windows-scope.md`, `BBF-FU-22-windows-contract-correction.md` and
  `BBF-FU20-network-skip-correction.md` — are in the same defect class and are
  **not** corrected by this flip. They are named in §5.1 rather than left inside
  an over-broad closure claim; they need their own flip.

## §5. The sweep, and the sites it initially missed

The first sweep for this class was too narrow: it searched for the *phrases*
used in the two BBF-86.7 passages ("unlanded", "absent from the base tree"),
and on that basis concluded that only two sites matched. That conclusion was
wrong, and an independent review of the first draft caught it. The defect was
in the **sweep**, not in the two corrections: a phrase search finds the
sentences that use those phrases, not the sentences that are stale in the same
way.

The widened sweep looks for the **shape** instead: any line in a per-flip brief
that asserts a present-tense status for a named FU or a merged config, then
checks that status against the ledger's own `**Status:**` line and against the
tree. Its first round produced these four passages:

| Brief | Passage | True when written | Live now |
|---|---|---|---|
| `BBF-doc-drift-flip.md` (2026-10-16) | the 13-FU exclusion table's "genuinely still OPEN" framing | yes | 10 of its 13 rows name FUs since resolved; FU-9, FU-23, FU-27 remain OPEN |
| `BBF-doc-drift-flip-7.md` (2026-10-19) | "The remaining OPEN FUs (FU-9, FU-11β, FU-23, FU-27) are genuinely unimplemented work" | yes | FU-11 resolved for the approved α-ext scope on 2026-11-04 |
| `BBF-doc-drift-flip-8.md` (2026-10-21) | "Does not touch FU-15, FU-42 … Both are still OPEN per the headline" | yes | FU-15 is FULLY RESOLVED; FU-42 is RESOLVED via PR #143 |
| `BBF-doc-drift-flip-13.md` (2026-10-27) | "The merged `.gitleaks.toml` names `lichess-pat` in `targetRules`" | yes | PR #184 removed that id the same day, after this brief landed |

This table is the **first round only**. Later rounds of the same sweep found
nine more passages, listed in §3.3's table: `flip-3`'s and `flip-4`'s
enumerated "still-open FUs" lists, `flip-12`'s three "external triage category"
assertions, `flip-13`'s §6 exclusion bullets, `flip-9c`'s quoted FU-20 status,
and the FU-2 exclusion bullets in `flip-8`, `flip-9a` and `flip-14` together
with FU-20's in `flip-10`. §3.3's table is the complete list of the thirteen
passages found by any sweep; §5.1 records the method that finally closed it.

Hits that were examined and are **not** in the class are left untouched:
`flip-9b`'s FU-15 pointer, `flip-21`'s FU-20 quotation, `flip-9a`'s and
`flip-9c`'s own scope descriptions, `flip-16`'s and `flip-17`'s "each
truthfully open" lists (their FU-7 entry was already `PARTIAL` when they were
written, so they are not later-measurement staleness), `flip-13`'s FU-38 step
(b) passage (already reconciled by the product-owner decision recorded directly
beneath it), `PROGRESS_REPORT_2026-09-03.md` (a dated snapshot with a pinned
source basis), and the ledger's own "separate BBF" passages (already carrying
their reconciliation).
### §5.1 The method that finally closed the sweep

The first two sweeps were both **phrase** searches and both reported closure
that was false:

1. The first searched for the phrases used in the two BBF-86.7 passages and
   reported two sites. It missed every site that used different words.
2. The second searched for a wider phrase set and reported six. It still
   missed `flip-3` and `flip-4`, which write "**still-open**" with a hyphen —
   a pattern the phrase list did not contain — and `flip-12`, whose claim is
   framed as a triage category rather than as an open/closed statement.

The method that closes the class is **structural, not lexical**: find every
line in a per-flip brief that asserts a *named FU's ledger-entry status* in the
present tense — using the ledger's own status vocabulary (`status reads`,
`leads with`, `PARTIALLY RESOLVED`, and so on) — and then check each named FU
against the ledger's own `**Status:**` line. One named FU is enough; the
earlier version of this method required two and would have missed the three
single-FU flip-12 sites. What matters is the *claim type*, not the count of
identifiers on the line: a hyphenated spelling, a triage-category phrasing,
and an enumerated list all match, because none of them depends on the wording. A quotation is
excluded by two independent tests: it sits inside a code fence, or it is
attributed to a named source. A historical record is excluded by its own
marker — "at the time of this flip", a dated "Historical state" block, or an
explicit "superseded" label.

Later reviews of the widened draft each found further members of the class and
one imprecision in an existing correction, all of which are corrected here: more
per-flip briefs assert a now-false current state, and one correction block had
inherited an over-statement from the sentence it preserves. The class is closed
at **fifteen passages** across **thirteen briefs**, plus this brief.

The count is derived once, from the diff, and used everywhere: fourteen files
change (thirteen earlier briefs plus this one), and those thirteen briefs carry
**fifteen** correction blocks. There is one block per corrected passage, so the
block count and the passage count are the same number. Two of the fifteen are
the BBF-86.7 pair (§3.1 and §3.2); the other thirteen are the rows of §3.3's
table. A block may cover more than one assertion — flip-12's block covers three
triage assertions, and flip-13's second block covers two exclusion bullets — but
those are sub-items of one passage, not additional passages.

**The sweep's scope is stated precisely.** It runs over the *per-flip briefs*
under `docs/16_audit/`, which is the class this flip corrects. Four documents in
`docs/16_audit/` that are **not** per-flip briefs also assert now-false states
— `BBF-FU-20-impl-windows.md` (the Windows memory cap, implemented by PR #190),
`BBF-FU-21-windows-scope.md` (the Linux bind-mount, implemented by PR #169),
`BBF-FU-22-windows-contract-correction.md` (quoting the same brief's §1/§5
contradiction), and `BBF-FU20-network-skip-correction.md` (the same
FU-20-versus-FU-22 mapping) — and they are **not** corrected by this flip. Each
was true when written and each is now overtaken, so they belong to the same
defect class; they are recorded here as a separate, named item rather than
silently left inside an over-broad closure claim. They need their own flip.

## §6. Why the corrections are safe to make now

The defect class here is the **later-measurement** one: a document says
something is not established, and a later measurement established it, so the
document now contradicts its own subject. The house rule is to state the measured
result in place of the stale sentence, or to label the old sentence as the
pre-correction historical state with a pointer to where the measurement landed.
Every corrected passage is now dated and labelled, and every one carries the
measurement.

No line-count constraint applies here. The ledger is not edited, so its geometry
and its pointer values are untouched. Some of the corrected briefs do cite the
ledger by line number — those citations are labels against their own bases and
remain accurate as history — but because the ledger is not edited, no
cross-file anchor arithmetic is needed. The edit is confined to Markdown files
under `docs/16_audit/`.

## §7. Exact scope

Fourteen files, all Markdown, all under `docs/16_audit/` — thirteen earlier
briefs modified, plus this new brief:

- `docs/16_audit/BBF-doc-drift-flip.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-3.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-4.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-7.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-8.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-12.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-13.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-15.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-16.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-9a.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-9c.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-10.md` — modified
- `docs/16_audit/BBF-doc-drift-flip-14.md` — modified

Plus this new brief. No source, test, workflow, configuration, lockfile,
default, or runtime-behaviour change.

## §8. Verification

- Every claim in each new correction block was re-derived against the tree at the
  pinned base: PR #199's merge SHA exists and is an ancestor of `main`; the
  corpus `_metadata.version` field is present; the Dockerfile `BUILD_ARG`
  flags are present with the stated values; both audit briefs read `Implemented by this
  BBF`; the release-readiness brief records `PR #48 is historical`; neither
  audit brief still claims BBF-86.7 is `shipped`; commit `f0253b0` is still not
  an ancestor of `main`; and the landing dates of flip-15, flip-16 and PR #199
  are as stated.
- The thirteen additional passages were each measured against their own brief's
  base, not against the current tree, so that each correction can say the claim
  was true when written: FU-11's `**Status:**` line read OPEN at flip-7's base;
  FU-42's read OPEN at flip-8's base while FU-15's already read PARTIAL; the
  merged `targetRules` still named `lichess-pat` at flip-13's own tree; PR #184
  merged the same day, at 13:59 local time against this brief's 12:22; all
  eight FUs in flip-3's list and all seven in flip-4's were still open or in
  progress at those briefs' own bases; each of flip-12's three quoted ledger
  strings was present at its own base; flip-13's two quoted mid-entry strings
  were present at its own base; FU-20's status read `PARTIALLY RESOLVED
  2026-10-18` at flip-9c's base and at flip-10's base; and FU-2's status read
  `PARTIALLY RESOLVED 2026-08-04` at flip-8's, flip-9a's and flip-14's bases.
  Each of the FUs named as resolved now carries a `**Status:**` line saying so,
  and the three that remain OPEN — FU-9, FU-23, FU-27 — still do.
- The one imprecision is recorded as such: at flip-8's base FU-15's own
  `**Status:**` line read `PARTIAL`, so flip-8's "both are still OPEN" wording
  was over-stated when written rather than overtaken later, and the correction
  says so instead of applying the later-measurement framing to it.
- Each edited passage retains its original claim in substance, marked with the
  date it was true, and gains exactly one inline
  `**Correction (2026-11-19, doc-drift fix-up):**` block.
- Byte integrity: LF-only, BOM-free, no mojibake. Trailing newlines are
  preserved, not added: `BBF-doc-drift-flip-9c.md` did not end with a newline
  before this flip and does not now, and `git diff --check` is clean because the
  change does not touch its last line.
- `git diff --check` clean; file modes unchanged.

## §9. Honest limitations

- **No runtime test was executed for this flip.** The change is prose in
  fourteen Markdown files with no behavioural surface; every measurement above is
  a static read of a named revision.
- **The first two sweeps for this class were too narrow and each reported a
  false negative.** The first searched for the phrases used in the two
  BBF-86.7 passages; the second widened the phrase list but still missed a
  hyphenated spelling and a triage-category phrasing. Both reported closure
  that was false, and both were caught by independent review. A third review
  then found two more sites and one imprecision that the structural sweep had
  also missed. The lesson is recorded in §5.1 and in the pitfall catalogue: a
  class sweep must match on **shape**, not on **wording**, or it will report
  closure it has not earned — and a sweep's own scope must be stated, so that
  what it did not cover is named rather than implied.
- **The thirteen briefs are historical records of what their flips concluded.** This
  BBF does not re-open any flip's scope decision — it records that a later
  landing discharged the scope the flip had excluded, or resolved an FU the flip
  had listed as open. The original reasoning, including the reasoning that was
  correct at the time, is preserved.
- **The `f0253b0` non-ancestry is left standing**, because it remains true.
- The correction does not touch the ledger, so the FU-20 entry and every other
  ledger entry are exactly as they were.
