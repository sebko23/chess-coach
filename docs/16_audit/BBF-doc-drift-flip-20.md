# BBF-doc-drift-flip-20 — correct the AppContainer landing date and three stale lifecycle markers

**Date:** 2026-11-17
**Type:** documentation maintenance (prose only, no behavioural surface)
**Base commit:** `7f027f64e824334cb0d3f925de1672a7910cc8ef`
**Corrects:** the `2026-11-09` implementation-date claim, the policy file's
self-description, and three briefs' stale `**Status:**` line

## §1. Why this flip exists

Three separate documentation defects, all of the same kind: **a claim that was
true when written and became false when the thing it describes changed.** They
are grouped here because they share one root cause class and one measurement
basis, and because each was independently surfaced and independently
confirmed.

**The date defect.** The Windows AppContainer implementation is described
across the tree as having landed on **2026-11-09**. The reviewed implementation
actually landed on `main` on **2026-11-11**, as the squash of PR #195. November 9 is
the date the implementation *work existed* — it was an early commit on PR #195's own
branch — so it is preserved wherever it describes the work, and corrected wherever it
was presented as the date the implementation reached `main`.

**The self-description defect.** The standing policy file describes itself as
untracked. It is tracked.

**The lifecycle-marker defect.** Three landed briefs still read
`**Status:** Draft for review`.

## §2. The date defect: lineage, measured

Two commits carry the subject *"fix(fu20): implement the Windows AppContainer
network-isolation backend"*:

| Commit | Date | Role | Ancestor of `main` |
|---|---|---|---|
| the branch's first commit — same subject, dated 2026-11-09 | 2026-11-09 | the **first of 13 commits on PR #195's own branch**, amended forward within that branch | **no** |
| `f57bfcc18d0833158b4f871d670c1160a99f998d` | 2026-11-11 | PR #195's **squash**, landed on `main` | **yes** |

Nothing was abandoned, and there were not two rival efforts. The 2026-11-09 commit
is the **first commit on PR #195's own branch** (`bbf-fu20-windows-appcontainer`); the
branch was amended forward across 13 commits through 2026-11-10, and the reviewed
implementation landed on `main` as the squash `f57bfcc1…` on 2026-11-11.

That distinction is measured, not inferred:

- the 2026-11-09 commit **is** an ancestor of PR #195's retained head — it sits *inside*
  the PR's own history, as the first of its 13 commits;
- PR #195's retained head and the landed squash have **identical trees** — the squash
  is that reviewed head's content, committed on 2026-11-11;
- PR #195's retained head is reachable as `refs/pull/195/head`;
- the 2026-11-09 commit is reachable from that same ref, and is **not** an ancestor of
  `main` — which is why the flip-rules ancestry gate rejects it and why this brief
  names it by subject and date rather than by SHA.

A reader who wants to see the 2026-11-09 commit must fetch the PR ref explicitly
(`git fetch origin refs/pull/195/head`). It is **not** present in a fresh clone: the
branch was deleted from `origin`, and `refs/pull/*` is not fetched by the default
refspec. A `git log --all --grep` over a fresh clone therefore surfaces only the
landed squash, never the 2026-11-09 commit.

Exactly one ref on the remote reaches it — `refs/pull/195/head`. No `refs/heads/*` on
the remote reaches it, and none on `main`. A host-local branch that predates the
remote deletion may still name it; that is local state, not the remote's.


So the truthful statement of the defect is: **the implementation work existed on
2026-11-09 as the first commit on PR #195's branch; the reviewed implementation landed
on `main` on 2026-11-11 through PR #195.** The November 9 date was never wrong as a
work-history fact — it was wrong wherever it was presented as the date the
implementation reached `main`.

### §2.1 The two kinds of date claim

The scope of this flip distinguishes them, because the two are not the same fact:

- A **current-state claim** — the implementation *is available*, *landed*, or
  *became the shipped opt-in backend* — is dated **2026-11-11**, the date the
  reviewed implementation reached `main`.
- A **historical work claim** — the work *existed* on a given day — keeps
  **2026-11-09**, because that is true: the branch's first commit carries that date.

Where a single sentence carried both, the correction names both: the landed
date, and the work date, explicitly.

## §3. The date sites, and what each becomes

| Site | Before | After |
|---|---|---|
| `OPEN-FOLLOWUPS.md` L1665 | "it was implemented on 2026-11-09" | "implemented on **2026-11-11** as squash `f57bfcc1` (PR #195; implementation work existed on 2026-11-09 …)" |
| `OPEN-FOLLOWUPS.md` L1667 | "**2026-11-09** Windows AppContainer implementation" | "**2026-11-11** Windows AppContainer implementation — squash `f57bfcc1` (PR #195; implementation work existed on 2026-11-09)" |
| `docs/08_security/security-strategy.md` L128 | "…available behind an opt-in flag (2026-11-09, `BBF-FU-20-windows-appcontainer-network-isolation`)" | "…(2026-11-11, squash `f57bfcc1`, PR #195, `BBF-FU-20-windows-appcontainer-network-isolation`)" |
| `docs/08_security/security-strategy.md` L133 | "**Windows AppContainer path (opt-in, 2026-11-09, …)**" | "**Windows AppContainer path (opt-in, 2026-11-11, squash `f57bfcc1`, PR #195, …)**" |
| `BBF-FU-20-impl-windows.md` L149 | "## §8. Superseded by the AppContainer implementation (2026-11-09)" | "## §8. Superseded by the AppContainer implementation (landed 2026-11-11, squash `f57bfcc1`, PR #195)" |
| `BBF-FU-20-impl-windows.md` L157 | "implemented on 2026-11-09 as a **zero-capability AppContainer**" | "implemented on 2026-11-11 as squash `f57bfcc1` (PR #195; implementation work existed on 2026-11-09) as a **zero-capability AppContainer**" |
| `BBF-FU-20-windows-appcontainer-network-isolation.md` L3 | "**Date:** 2026-11-09" | "**Date:** 2026-11-09 (implementation work)" plus a new line "**Landed on `main`:** 2026-11-11 as squash `f57bfcc1` (PR #195)" |

Each site is a **substitution within one physical line** except the last, which
splits one header line into two. The ledger's two edits are one-line-for-one-line.

## §4. The self-description defect

The standing policy file's persistence section read:

```text
- This document lives at `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` (untracked,
  per the project's `docs/16_audit/` convention).
```

That is false in the same way the ledger's header was false: the file **is**
tracked (added by squash `d3c5a18a`, 2026-08-10) and is **not** ignored
(`git check-ignore` does not match it). It is replaced by two lines:

```text
- This document lives at `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` and is
  **tracked** in git (added by squash `d3c5a18a`, 2026-08-10); it is not ignored.
```

Two lines become two lines.

## §5. The lifecycle-marker defect

Three landed briefs still carried `**Status:** Draft for review` at L3:
`BBF-doc-drift-flip-16.md`, `BBF-doc-drift-flip-17.md`, and
`BBF-doc-drift-flip-18.md`. All three are merged and CI-verified.

The replacement follows the landed house convention: a **scope** descriptor that
states what the brief changed, rather than a lifecycle marker. The landed briefs
(`flip-3`, `flip-4`, `flip-8`, `flip-9a`/`9b`/`9c`, `flip-10` through `flip-15`) all
use that shape, and the file count in it is the brief's own landed scope:

```text
**Status:** Doc-only BBF. 2 files modified (`docs/16_audit/OPEN-FOLLOWUPS.md` modified, `docs/16_audit/BBF-doc-drift-flip-16.md` NEW per-flip brief).
```

A scope descriptor does not rot: it describes what the brief changed, not where the
brief sits in a workflow. A lifecycle marker necessarily does — which is why
`Draft for review` was wrong for briefs that had already landed.

The three briefs' own landed scopes differ, and each status line states its own:

| Brief | Landed scope | Status line |
|---|---|---|
| flip-16 | 2 files | `Doc-only BBF. 2 files modified (…OPEN-FOLLOWUPS.md modified, …BBF-doc-drift-flip-16.md NEW per-flip brief)` |
| flip-17 | 3 files | `Doc + config BBF. 3 files modified (.env.example modified, …OPEN-FOLLOWUPS.md modified, …BBF-doc-drift-flip-17.md NEW per-flip brief)` |
| flip-18 | 2 files | `Doc-only BBF. 2 files modified (…OPEN-FOLLOWUPS.md modified, …BBF-doc-drift-flip-18.md NEW per-flip brief)` |

flip-17 is **not** doc-only: its landed squash also added 16 commented lines to
`.env.example`, a configuration file. Its status line says so rather than claiming a
doc-only scope it did not have.

The three landed squash SHAs are recorded once, here, rather than three times in the
briefs themselves:

| Brief | Landed squash | PR |
|---|---|---|
| flip-16 | `882972de8728bf4c36355dbf438aaf986bc8e093` | #198 |
| flip-17 | `42a6a400cf37911d15dc8edcd744000945c6fcdc` | #201 |
| flip-18 | `c79c6f4b3f3527811962d72a980b0094a3b32aa4` | #202 |

A sweep of every `**Status:**` line in the **tracked** `docs/16_audit/` tree for a
draft-shaped marker found exactly these three — no fourth instance. (Untracked
working-tree briefs under `docs/16_audit/` also carry `**Status:** DRAFTED` lines;
they are outside the tracked tree and outside this flip's scope.)

## §6. Historical quotations are preserved byte-identically

Three briefs record that earlier flips deliberately **excluded** the date
correction:

- `BBF-doc-drift-flip-17.md` L227,
- `BBF-doc-drift-flip-18.md` L138,
- `BBF-doc-drift-flip-19.md` L108.

Those are **historical records of a deferral**, not claims about the current
date. Editing them would falsify the audit trail — the same reason flip-19's
correction block exists rather than an in-place rewrite of flip-18's §1.

**They are byte-identical after this flip.** The `Draft for review` edits are at
L3 of the first two, and flip-19 is not touched at all.

**This flip supersedes those three deferrals.** The correction they deferred is
now made, and this brief is the record of it.

## §7. Exact scope

Nine files change:

| File | Change |
|---|---|
| `docs/16_audit/BBF-doc-drift-flip-16.md` | L3 status line |
| `docs/16_audit/BBF-doc-drift-flip-17.md` | L3 status line; L227 untouched |
| `docs/16_audit/BBF-doc-drift-flip-18.md` | L3 status line; L138 untouched |
| `docs/16_audit/OPEN-FOLLOWUPS.md` | L1665, L1667 — one line each, net 0 |
| `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` | L1445-L1446 — two lines, net 0 |
| `docs/08_security/security-strategy.md` | L128, L133 — one line each, net 0 |
| `docs/16_audit/BBF-FU-20-impl-windows.md` | L149, L157 — one line each, net 0 |
| `docs/16_audit/BBF-FU-20-windows-appcontainer-network-isolation.md` | L3 header split into two lines |
| `docs/16_audit/BBF-doc-drift-flip-20.md` | this brief |

No source, test, workflow, configuration, lockfile, or default changes. No
runtime behaviour changes. **No change to FU-20's opt-in/default decision.**

## §8. Why ledger line-count neutrality is load-bearing here

PR #194 landed ten `**Original entry:** lines N-M` pointers in this ledger whose
**values are line numbers**. All ten sit at ledger lines 3568-3848, well below
both edited lines.

The two ledger edits are **one line replaced by one line** each, so the ledger
stays at **3,884 lines** with its trailing newline intact, and every pointer
value is unchanged and still resolves. A net line change here would silently
re-point them at the wrong FU entries — the defect class PR #194 was merged to
fix, and one no CI gate in this repository can catch.

## §9. Verification

- the ledger stays at 3,884 lines, trailing newline preserved, LF-only, no BOM;
- exactly two ledger lines differ from the base (1665, 1667); every other line
  is byte-identical;
- all ten PR #194 pointer values are unchanged and resolve to their referenced
  FU headings;
- the three historical quotations are byte-identical to the base;
- `git diff --check` is clean; no file-mode regressions;
- the flip-rules gate passes in manifest mode: scope, numstat, SHA ancestry, and
  content anchors — each anchor verified in its own invocation, because
  `--anchor` and `--preserve` are last-wins flags;
- the gate is proven **non-vacuous**: a wrong numstat, a wrong file set, wrong
  anchors, and a genuinely non-ancestor SHA are each rejected with a non-zero
  exit;
- the commit-reference gate passes, and rejects an out-of-range `path:NNN` and a
  non-existent file when unbackticked;
- every SHA named in this brief, in the commit body and in the PR body is an
  ancestor of the base — the flip-rules ancestry gate enforces this for both
  bodies;
- the measured numstat is `+13/-12` across the eight corrected files, plus this
  brief.

**No runtime test was executed for this change.** The change is prose in nine
markdown files with no behavioural surface; every measurement above is a static
read of a named revision.

## §10. Explicit exclusions

- **The three historical quotations** in flip-17, flip-18 and flip-19. Preserved
  byte-identically; see §6.
- **FU-20's lead status line and its `**Status:** OPEN` line.** The lead is
  accurate as it stands; the `OPEN` line is preserved history under a
  `RESOLVED` lead. flip-16, flip-17 and flip-18 all recorded the same
  reasoning, and it still holds.
- **Decision B (the shipped-default flip).** Not requested here.
- **The Windows filesystem-isolation property (A-F11 property 3).** A
  deployment-config concern (AppLocker/WDAC), unaffected by any date wording.
- **The loose ledger mirror and the container's ledger copies.** Outside this
  repository; not touched by this flip.
- **The two sibling worktrees** `cc-audit` and `cc-phase8`. Each is correct
  against its own HEAD; not touched.

## §11. Honest limitations

- **No runtime test was executed.** Prose only.
- **This flip does not re-verify anything about the AppContainer
  implementation's behaviour.** It corrects the date attributed to a landed
  commit. The implementation's own behaviour was verified by its own BBFs and
  its own native-Windows CI.
- **The `2026-11-09` date is preserved as a work-history fact** wherever it
  describes the work rather than the landing. A reader who sees both dates in
  one sentence is seeing two different facts, not a contradiction.
- **This flip does not claim the tree is free of further stale claims.** It
  corrects the ones it measured, by sweep rather than by inspection: the
  `2026-11-09` class was swept across every tracked `.md` file, and the
  draft-status class across every `**Status:**` line in `docs/16_audit/`.
