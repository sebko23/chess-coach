# BBF-doc-drift-flip-23 — retire FU-20's stale mid-entry status line and correct the seven non-flip briefs

**Date:** 2026-11-24
**Type:** documentation maintenance (prose only, no behavioural surface)
**Base commit:** `3c16a0b9eeb6672db8beea99e750bf10be2daa50`
**Corrects:** thirty stale current-state claims in sixteen existing files (seventeen with this brief) — FU-20's mid-entry
`**Status:** OPEN` line in the ledger, the seven non-flip briefs (the four that
`BBF-doc-drift-flip-22` named as needing their own flip, and the three it did
not name), and the eight earlier
flip briefs whose passages that ledger line made stale

## §1. What this BBF does

Three defects, all of the same class as the flip-22 work, across sixteen
existing files and thirty passages: a present-tense
claim about a scope or a status that a later landing made false.

1. **The ledger.** FU-20's entry carries a second `**Status:**` line, inside its
   preserved `**Identified:**` / `**The gap:**` historical body, that still reads
   `**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:` — while
   the entry's own lead reads `RESOLVED for the named release scope
   (2026-10-30)`. The line is retired here, the way `BBF-doc-drift-flip-10`
   retired FU-21's stale line of the same class - the two differ in wording,
   which is why an exact-string grep for the FU-21 line does not match this one -
   and the way `flip-9b` and `flip-9c`
   retired FU-17's and FU-19's.
2. **The seven non-flip briefs.** `BBF-doc-drift-flip-22` §4 named
   `BBF-FU-20-impl-windows.md`, `BBF-FU-21-windows-scope.md`,
   `BBF-FU-22-windows-contract-correction.md` and
   `BBF-FU20-network-skip-correction.md` as being in the same defect class and
   explicitly **not** corrected by that flip, rather than left inside an
   over-broad closure claim. They are corrected here, along with
   `BBF-FU-20-impl.md` and `BBF-FU-21-impl.md`, whose cross-references assert
   the same pending flip in the same forward-looking shape and which flip-22's
   four-brief list did not name, and `BBF-FU-20-21-22-A-F11-spikes.md`, whose
   `**Honest disclosures:**` bullet asserted in the present tense that all three
   of FU-20/21/22 carried that ledger line - true for FU-20 alone, and retired
   since.
3. **The eight earlier flip briefs.** Retiring the ledger line makes the
   passages in `BBF-doc-drift-flip-10.md`, `-12.md`, `-13.md`, `-16.md`,
   `-17.md`, `-18.md`, `-20.md` and `-4.md` that describe that line as still
   live, or FU-20's status as still `PARTIALLY RESOLVED`, stale in turn. They
   are corrected in the same flip, because a fix that leaves its own downstream
   claims false is not a fix.

Every correction preserves the original claim as the dated historical reading
and states the live status. Nothing is deleted. The scope decision each
original flip made is not re-opened — only its current-state claim is
corrected.

## §2. Why FU-20's mid-entry line is stale

The line dates from 2026-08-13, when FU-20 was identified. It records the
position at that moment: neither the Linux network-namespace path nor the
Windows Job-Object path existed.

Both have since been implemented and measured:

| Path | Landed | What exists now |
|---|---|---|
| Linux | 2026-11-02 (BBF dated 2026-10-29) | `services/chess_coach/pdf_ocr/linux_sandbox.py` — one dedicated launcher owning a single `unshare(CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS)` namespace lifecycle, enforced **fail closed** |
| Windows | 2026-11-11 | `services/chess_coach/pdf_ocr/windows_appcontainer.py` — a **zero-capability** AppContainer behind the opt-in flag `CHESS_COACH_WINDOWS_APPCONTAINER=1` |

The Windows boundary is opt-in, so the shipped default remains the 501
`internal.not_implemented` refusal, and **FU-20 deliberately remains open** as
the standing per-deployment enablement item. Decision A was accepted generally
on 2026-11-17 as available-for-enablement; Decision B was not accepted. The
retirement of the stale line does not close FU-20.

## §3. The thirty passages, and what each becomes

### §3.1 The ledger — FU-20's mid-entry status line

| File | Passage | Becomes |
|---|---|---|
| `docs/16_audit/OPEN-FOLLOWUPS.md` | FU-20's mid-entry `**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:` | The live status, plus an explicit superseded marker naming both implementations. The investigation plan beneath it is preserved **verbatim**. |

The edit is **one line for one line**: the ledger's line count is unchanged, so
the ten `**Original entry:** lines X-Y` pointers, which reference current line
numbers, all still resolve to the same lines. The shape follows flip-10's
retirement of FU-21's line: the status line is replaced and the plan beneath it
is retained.

### §3.2 The seven non-flip briefs

| File | Passage | Becomes |
|---|---|---|
| `BBF-FU-20-impl-windows.md` | The Sprint intent's "The ideal Windows implementation would use a Job Object with `JOB_OBJECT_NET_RATE_CONTROL`" and §1's item 3, "AppContainer (requires significant new code)" | Superseded: the AppContainer backend landed 2026-11-11. §8 of that brief already records it. |
| `BBF-FU-20-impl-windows.md` | §5's "**The `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (memory cap on Windows)** is still not implemented" | Superseded: `services/chess_coach/pdf_ocr/windows_job.py` implements the cap through `ctypes`, landed 2026-10-29 as PR #190. That brief's own 2026-10-28 §7 correction was accurate then and is now itself superseded. |
| `BBF-FU-20-impl-windows.md` | §6's "FU-20 entry (will be flipped to PARTIALLY RESOLVED in a follow-up doc-drift-flip)" | Superseded: the entry was flipped, and further — its lead now reads `RESOLVED for the named release scope (2026-10-30)`. |
| `BBF-FU-21-windows-scope.md` | §1.3's "There is no **FU-21-windows-impl** BBF coming. The open work for FU-21 is:" and its item 1, "**The bind-mount follow-up BBF**" | Superseded: the bind-mount BBF landed 2026-10-19 as PR #169 (`d3fbb35c`), the same day this brief was written; FU-21 is `RESOLVED 2026-10-19` on both the Linux and the Windows deployment-config surface. The deployment-config / AppLocker-WDAC artifact remains a deployment-team concern in another repo. |
| `BBF-FU-21-windows-scope.md` | §6's "**The Linux FU-21 bind-mount BBF is still open.**" | Superseded: the same landing as the row above - the bind-mount BBF landed 2026-10-19 as PR #169 (`d3fbb35c`), which post-dates this brief by the same day. |
| `BBF-FU-22-windows-contract-correction.md` | §6 "Outstanding — B2 (separately approved; **not** implemented here)" | Discharged: B2 landed 2026-10-29 as PR #190. The `pywin32` dependency it listed was **not** added, because the implementation uses `ctypes`. |
| `BBF-FU-22-windows-contract-correction.md` | The Sprint intent's "the Windows half was never implemented" | Accurate as of 2026-10-28; superseded by B2. Windows enforcement now exists and is directly tested. |
| `BBF-FU-22-windows-contract-correction.md` | §1's "FU-20 is A-F11 property 2 (network isolation) and is `PARTIALLY RESOLVED` since PR #163/#164 (`4c11159c` / `fa0bfd73`, 2026-10-18)" | The reading on 2026-10-28. FU-20 now leads `RESOLVED for the named release scope (2026-10-30)`. |
| `BBF-FU20-network-skip-correction.md` | §1's "`set_network_isolation_preexec()` exists at `services/chess_coach/pdf_ocr/subprocess_runner.py` L128" and §7's L182–183 / L206–242 / L600– citations | Superseded: the helper was **retired** by the `BBF-FU-20-linux-phase1-network-isolation` landing, squash `df3ed9bf` (2026-11-02). The current guard is `ensure_network_isolation_supported()`; the cited line numbers no longer resolve. |
| `BBF-FU20-network-skip-correction.md` | §3's "the implementation's own comment at L182–183 says a determined attacker can still open raw sockets" | The caveat still holds in substance, but it is now stated by the landed `NetworkIsolationUnsupportedError` class docstring in `services/chess_coach/pdf_ocr/subprocess_runner.py`: *"Job Object network-rate control is throttling rather than isolation. Proxy-environment stripping is defense in depth, never isolation."* The skip's own `SKIP` disposition is unchanged. |
| `BBF-FU20-network-skip-correction.md` | §3's "enforced on Linux (FU-20, PRs #163/#164) but not on Windows (best-effort proxy-env stripping" | Superseded as a description of the live implementation: Windows PDF parsing runs in the zero-capability AppContainer backend, and while the opt-in is off the route keeps the 501 refusal rather than falling back to the best-effort path. |
| `BBF-FU20-network-skip-correction.md` | §4's "**Does not claim Windows network isolation.** The Windows path remains proxy-env stripping, a defense-in-depth measure" | Superseded as a description of the live implementation: the proxy-environment stripping fallback was itself removed from the production path, and Windows PDF parsing runs in the zero-capability AppContainer backend. |
| `BBF-FU-20-impl.md` | §5's cross-reference "FU-20 entry (to be flipped to PARTIALLY RESOLVED in a follow-up doc-drift-flip)" | It was flipped, and further: FU-20 now leads `RESOLVED for the named release scope (2026-10-30)`, and the AppContainer backend landed 2026-11-11. |
| `BBF-FU-21-impl.md` | §5's cross-reference "FU-21 entry (to be flipped to PARTIALLY RESOLVED in a follow-up doc-drift-flip)" | It was flipped the same day: FU-21 now leads `RESOLVED 2026-10-19 via PR #169`. |
| `BBF-FU-21-impl.md` | The Sprint intent's "the Windows path remains a no-op (genuine isolation requires AppLocker/WDAC, a follow-up BBF)" | Superseded: the follow-up BBF landed the same day as PR #169 (`d3fbb35c`), giving the Linux path full read-only filesystem enforcement. The deployment-config / AppLocker-WDAC artifact remains a deployment-team concern in another repo. |
| `BBF-FU-20-21-22-A-F11-spikes.md` | The `**Honest disclosures:**` bullet's `Per the ledger entries for FU-20/21/22, each property is "Real contract gap, but heavy-lift caveat applies."` | Partly true when written (FU-20's mid-entry line only) and over-stated for FU-21/FU-22; the line has since been retired. |
Sixteen passages across these seven briefs. The table's sixteen rows and the
count model's "16 in the seven non-flip briefs" are the same sixteen; §3.1's
single row and §3.3's thirteen rows make the thirty.

### §3.3 The eight earlier flip briefs

Retiring the ledger line changes what these passages say about it. Each is
corrected from "still live" to "was live at the time, retired on 2026-11-24".

| File | Passage | Becomes |
|---|---|---|
| `BBF-doc-drift-flip-10.md` | §6's "The quoted mid-entry line was still present and still live at the time of this correction, on 2026-11-19" | Retired by this flip. |
| `BBF-doc-drift-flip-10.md` | §1's "**FU-20 is NOT clean, and this flip does not fix it.** Its entry leads with `PARTIALLY RESOLVED 2026-10-18` (L1637) but still carries a stale `**Status:** OPEN. Real contract gap, but heavy-lift caveat applies:` at **L1664**" | Retired by this flip. |
| `BBF-doc-drift-flip-10.md` | §4's "**Does not touch FU-20**, which has the same defect class at L1664" | Retired by this flip; the separate flip it called for was this one, and the class sweep it recommended was done. |
| `BBF-doc-drift-flip-12.md` | §3's "The quoted mid-entry string was still present in the ledger at the time of this correction, sitting under a lead that had been superseded" | Retired by this flip. |
| `BBF-doc-drift-flip-13.md` | §6's "FU-20's quoted mid-entry line was still in the ledger at the time of this correction, sitting under a lead that then read `RESOLVED for the named release scope (2026-10-30)`" | Retired by this flip. |
| `BBF-doc-drift-flip-16.md` | §6's "FU-20 ... It is historical content, not a contradiction to correct, and touching it would delete history" | Retired by this flip, with the investigation plan preserved verbatim — so no history was deleted. |
| `BBF-doc-drift-flip-17.md` | §3's byte-for-byte list naming "the `**Status:** OPEN` line at 1764" | Annotated: the line was present when that flip landed and was retired later. |
| `BBF-doc-drift-flip-17.md` | §8's "FU-20's `**Status:** OPEN` line (1764) ... it still holds" | Retired by this flip. |
| `BBF-doc-drift-flip-17.md` | §4's "**FU-20 remains open** after this flip, because the product-enablement decision has not been taken" | Superseded: the decision was taken on 2026-11-17 (Decision A accepted generally, Decision B not accepted). What remains open is per-deployment activation, not the decision. |
| `BBF-doc-drift-flip-17.md` | §7's gate-anchor row `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1764=Status:** OPEN` | Annotated: that was that flip's own gate spec, against a tree that has since changed. |
| `BBF-doc-drift-flip-18.md` | §7's "FU-20's lead status line and its `**Status:** OPEN` line ... the `OPEN` line is preserved history under a `RESOLVED` lead ... and it still holds" | Retired by this flip. |
| `BBF-doc-drift-flip-20.md` | §10's "FU-20's lead status line and its `**Status:** OPEN` line ... the `OPEN` line is preserved history under a `RESOLVED` lead ... and it still holds" | Retired by this flip. |
| `BBF-doc-drift-flip-4.md` | §4's "FU-20 is PARTIALLY RESOLVED ... The Windows path is best-effort (env-var stripping only)" | Superseded: FU-20 now leads `RESOLVED for the named release scope (2026-10-30)` and the Windows path is the AppContainer backend, not proxy stripping. |

## §4. The count model

Every count below is derived from the diff, and the identity that ties the
parts together is asserted rather than repeated:

| Quantity | Value |
|---|---|
| Files changed | **17** |
| — the seven non-flip briefs | 7 |
| — the eight earlier flip briefs | 8 |
| — the ledger | 1 |
| — the new brief for this flip | 1 |
| Distinct passages corrected | **30** |
| — in the seven non-flip briefs | 16 |
| — in the eight earlier flip briefs | 13 |
| — in the ledger | 1 |
| **16 + 13 + 1 = 30** | ✓ |
| Correction blocks added | 17 |
| Ledger line-count change | 0 (one line for one line) |

## §5. What is NOT edited

- **FU-20's scope.** The retirement of the stale line does not close FU-20.
  It remains the standing per-deployment enablement item: Decision A accepted
  generally on 2026-11-17 as available-for-enablement, subject to the
  enablement contract's per-deployment staging, package-profile and
  residual-limitation requirements; actual enablement remains an operational
  decision for each deployment. Decision B was not accepted — the shipped
  default remains the 501 `internal.not_implemented` refusal, and no parser
  process, Job target, or AppContainer is created while the opt-in is disabled.
- **The ledger's other entries.** FU-21's mid-entry line was retired by
  flip-10 and FU-22's by flip-12; PR #190 later replaced FU-22's *lead* status
  line, not its mid-entry line. Nothing else in the ledger is touched.
- **The ten `**Original entry:**` pointers.** The ledger edit is line-count
  neutral, so every pointer still resolves to the same line it did at the base.
- **Any source, test, workflow, configuration, lockfile, or generated file.**
  The diff is Markdown only.
- **The `picomatch` advisory.** FU-49's ledger entry already records it
  truthfully: the advisory `GHSA-fc5q-39xc-vjpf` / `CVE-2026-112366` was
  **withdrawn** on 2026-11-18, no upstream `>= 4.0.8` exists, and the prod
  audit's green state comes from that withdrawal rather than from a
  remediation. That is unchanged and is not re-litigated here.
- **The remote branch inventory.** The stale remote branches were deleted
  outside this flip; see §7.

## §6. Why the corrections are safe to make now

Each corrected claim was measured against the landed tree, not inferred:

- **The Windows memory cap.** `services/chess_coach/pdf_ocr/windows_job.py`
  calls `CreateJobObjectW`, `SetInformationJobObject` with
  `JobObjectExtendedLimitInformation`, and sets
  `JOB_OBJECT_LIMIT_PROCESS_MEMORY` at 2 GiB; the target is created suspended
  and resumed only after Job assignment.
- **The Linux boundary.** `services/chess_coach/pdf_ocr/linux_sandbox.py` owns
  the `CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS` namespace lifecycle, and
  `scripts/dev/verify_linux_network_isolation.py` measures it in the
  production container.
- **The Windows boundary.**
  `services/chess_coach/pdf_ocr/windows_appcontainer.py` launches the parser
  with an empty capability array, so the token holds no `internetClient`
  capability.
- **The retired helper.** `set_network_isolation_preexec`,
  `set_rlimit_as_preexec` and `set_fs_isolation_preexec` are **no longer defined** in the landed tree's `*.py` sources: `git grep` finds zero `def` for any of them, and `tests/unit/test_subprocess_runner.py` asserts `not hasattr(runner, <name>)` for each. The names survive only as prose in comments and as test-function names that document the retirement.
  The commit that removed them is `df3ed9bf`
  (2026-11-02), the squash that landed the
  `BBF-FU-20-linux-phase1-network-isolation` implementation and the
  release-scope closure; `git log -S set_network_isolation_preexec` on
  `subprocess_runner.py` returns exactly that commit as the removal.
- **The FU-21 bind-mount.** FU-21's ledger entry reads `RESOLVED 2026-10-19
  via PR #169`.

## §7. Verification

- Semantic anchor checks against the committed tree, one invocation per
  specification.
- Preservation proof for the ledger, comparing the same line ranges in base
  and head.
- `git diff --check` clean; every changed file LF-only with no BOM.
- Byte-identity proof for the files this flip does **not** change.
- The two citation gates pass against both the commit body and the PR body.
- Every independent review round found real defects, and each one was a
  passage, a quotation or a count the preceding sweep had missed. The rounds
  found, in order: uncovered passages in `BBF-doc-drift-flip-10.md` §1 and §4;
  a count model that contradicted its own table; a wrong landing date
  attributed to `df3ed9bf`; the same claim shape in `BBF-doc-drift-flip-18.md`
  §7 and `BBF-doc-drift-flip-20.md` §10; section citations that pointed at the
  wrong section and quotations that were not verbatim; uncovered passages in
  `BBF-doc-drift-flip-4.md`, `BBF-FU-20-impl.md` and `BBF-FU-21-impl.md`; a
  seventh non-flip brief, `BBF-FU-20-21-22-A-F11-spikes.md`, whose
  `**Honest disclosures:**` bullet asserted in the present tense that all three
  of FU-20/21/22 carried that ledger line - true for FU-20 alone; and finally
  a live claim in `BBF-FU-21-windows-scope.md` §1.3 that no correction block
  covered. All are corrected here, and the count model above is the amended
  one: its three parts are the §3.1, §3.2 and §3.3 table rows, so it is
  checkable against the tables.

## §8. Honest limitations

- **The sweep's scope.** The final sweep ran over every one of the 97 Markdown
  files under `docs/16_audit/` and matched on the CLAIM SHAPE - a paragraph that
  references FU-20's status line and asserts a present-tense state for it -
  rather than on a fixed phrase list, because the earlier rounds each missed
  sites by exactly that difference. Every candidate it surfaced was classified
  as one of: covered by a correction block; a quotation or attributed
  historical snapshot; a claim about the original flip's own base tree where
  the line genuinely was present; or a description of this flip's own work.
  The corrected passages are the 30 rows of the §3.1, §3.2 and §3.3 tables,
  and the correction blocks added are counted across the 16 changed files.
- **The ledger's line count is unchanged, but the content of one line is
  different.** Any external reference to that line's former content must be
  re-read; the eight briefs in §3.3 are the ones found in this repository.
- **FU-20 remains open.** This flip makes the ledger truthful about FU-20; it
  does not resolve the per-deployment enablement decision.
- **The `picomatch` remediation remains upstream-blocked.** No `picomatch`
  release newer than `4.0.7` exists, so the prod gate's green state continues
  to rest on the advisory's withdrawal rather than on a fix.
