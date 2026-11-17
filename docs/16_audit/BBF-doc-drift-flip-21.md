# BBF-doc-drift-flip-21 — record the FU-20 Windows enablement decision

**Date:** 2026-11-17
**Type:** documentation maintenance (prose only, no behavioural surface)
**Base commit:** `849a63880f6d15324942419094323ebcd47a1607`
**Corrects:** the claim that the FU-20 Windows product-enablement decision had
not been taken

## §1. What this BBF does

Records a **product-owner decision** in the places that assert the decision is
still pending.

The decision, in the product owner's words:

- **Decision A — accepted generally.** The Windows AppContainer path is
  **available for per-deployment enablement**. The product accepts the
  implementation as a supported opt-in path; actual activation remains a
  per-deployment operational decision.
- **Decision B — not accepted.** The shipped 501 `internal.not_implemented`
  refusal is **not** retired and the default is **not** flipped.

**FU-20 remains open** as the standing enablement item.

The decision changes no code, default, workflow, configuration, lockfile, or
runtime behaviour. It changes six sentences that said the decision had not been
taken.

## §2. Why these sentences were false

Six live sites asserted one of two things that the decision made false:

- *"production enablement is a separate product decision **that has not been
  taken**"* — no longer true;
- *"**pending** the product-enablement decision"* — no longer true.

The five files carrying those sentences are the ledger entry itself, the
enablement contract, the implementation brief, and the security strategy. The
ledger carries two of them.

## §3. The six sites, and what each becomes

| # | Site | Before | After |
|---|---|---|---|
| 1 | `OPEN-FOLLOWUPS.md` L1667 | "…production enablement is a separate product decision **that has not been taken**…" | records Decision A accepted generally on 2026-11-17, Decision B not accepted, and that FU-20 deliberately remains open |
| 2 | `OPEN-FOLLOWUPS.md` L1682 | "**What genuinely remains open is the product-enablement decision**" | records that the decision was taken on 2026-11-17 and that what remains open is **per-deployment activation** |
| 3 | `BBF-FU-20-windows-appcontainer-enablement-contract.md` L186 | "FU-20 remains **open**, **pending** the product-enablement decision" | "FU-20 remains **open**, as the standing enablement item — Decision A accepted generally on 2026-11-17 … Decision B was not accepted" |
| 4 | `BBF-FU-20-windows-appcontainer-enablement-contract.md` L7 | "**Status:** contract only — **no code change, no default flip**" | **unchanged** — it remains exactly true |
| 5 | `BBF-FU-20-windows-appcontainer-network-isolation.md` L5 | "**FU-20 is NOT marked resolved** — production enablement is a separate product decision" | "**FU-20 is NOT marked resolved** — Decision A accepted generally on 2026-11-17 … Decision B was not accepted …" |
| 6 | `BBF-FU-20-windows-appcontainer-network-isolation.md` L377 | "**Until the enablement decision**, Windows PDF parsing is still refused." | "**Until the opt-in is enabled**, Windows PDF parsing is still refused." |
| 7 | `docs/08_security/security-strategy.md` L133 | "…production enablement is a **separate, explicitly reviewed product decision**." | records Decision A accepted generally and Decision B not accepted |

Site 4 is listed because it is in the decision class and was **deliberately left
alone**: "contract only — no code change, no default flip" is still exactly
true, because the decision changed neither.

Site 6 changes a different claim than the other five. It did not say the
decision was pending; it said that **until the decision, parsing is refused**.
The decision has now come, but parsing is still refused — because the
**default** did not move, not because the decision is outstanding. The clause
was corrected to name the opt-in, which is the thing that still gates the path.

## §4. Historical records are NOT edited

Three sites state the same pending-decision claim, and they are **left
byte-identical**:

- `BBF-doc-drift-flip-17.md` L122 — "FU-20 remains open after this flip,
  because the product-enablement decision has not been taken. The flip records
  the decision's surface; it does not make the decision." — **that was true
  when flip-17 landed**, and flip-17's own record of it is the audit trail.
- `BBF-doc-drift-flip-17.md` L95 and `BBF-doc-drift-flip-13.md` L43 — the same
  class, in those flips' own context.

Editing them would falsify the record of what those flips said at the time.
This flip supersedes the deferral, exactly as flip-20 superseded the earlier
date-correction deferrals.

## §5. What is unchanged, and must stay unchanged

The decision is a **product** decision. It changes nothing about behaviour:

- the shipped default remains the **501 `internal.not_implemented`** refusal;
- **no parser process, Job target, or AppContainer is created** while the
  opt-in is disabled;
- `CHESS_COACH_WINDOWS_APPCONTAINER=1` remains the explicit per-deployment
  activation switch, evaluated at **call time**;
- the implementation's network-isolation claim remains limited to the proven
  **AppContainer network boundary** — A-F11 property 2;
- **A-F11 property 3** (Windows read-only filesystem) remains **not enforced
  at the process level**; it stays a deployment-config concern (AppLocker/WDAC);
- the enablement contract's per-deployment **staging**, **package-profile**, and
  **residual-limitation** requirements are unchanged and still bind each
  enabling deployment.

## §6. Why the ledger edit is line-count neutral

PR #194 landed ten `**Original entry:** lines N-M` pointers in this ledger whose
**values are line numbers**. All ten sit at ledger lines 3568-3848, far below
both edited lines.

Both ledger edits replace **one line with one line**, so the ledger stays at
**3,884 lines** with its trailing newline intact, and every pointer value is
unchanged and still resolves. A net line change here would silently re-point
them at the wrong FU entries — the defect class PR #194 was merged to fix, and
one no CI gate in this repository can catch.

The other three files have no pointer geometry and keep their line counts too.

## §7. Exact scope

Five files change, all Markdown:

| File | Change |
|---|---|
| `docs/16_audit/OPEN-FOLLOWUPS.md` | L1667 and L1682 — one line each, net 0 |
| `docs/16_audit/BBF-FU-20-windows-appcontainer-enablement-contract.md` | L186 — one line |
| `docs/16_audit/BBF-FU-20-windows-appcontainer-network-isolation.md` | L5 and L377 — one line each |
| `docs/08_security/security-strategy.md` | L133 — one line |
| `docs/16_audit/BBF-doc-drift-flip-21.md` | this brief |

No source, test, workflow, configuration, lockfile, default, or runtime-behaviour
change. **No change to the Windows opt-in/default decision.**

## §8. Verification

- the ledger stays at 3,884 lines, trailing newline preserved, LF-only, no BOM;
- exactly two ledger lines differ from the base (1667, 1682); every other line
  is byte-identical;
- all ten PR #194 pointer values are unchanged and resolve to their referenced
  FU headings;
- the three historical quotation sites are byte-identical to the base;
- every edited site now names the decision's date and both decisions' outcomes;
- `git diff --check` is clean; no file-mode regressions;
- the flip-rules gate passes in manifest mode: scope, numstat, SHA ancestry, and
  content anchors — each anchor verified in its own invocation, because
  `--anchor` and `--preserve` are last-wins flags;
- the gate is proven **non-vacuous**: a wrong numstat, a wrong file set, wrong
  anchors, and a genuinely non-ancestor SHA are each rejected with a non-zero
  exit;
- the commit-reference gate passes, and rejects an out-of-range `path:NNN` and a
  non-existent file when unbackticked;
- the only SHA this flip names is the pinned base, which is trivially its own
  ancestor; the commit body and the PR body name no SHA at all, so the ancestry
  gate is exercised through `--require-ancestor` for the SHAs this flip cites.

**No runtime test was executed for this change.** The change is prose in five
markdown files with no behavioural surface; every measurement above is a static
read of a named revision.

## §9. Honest limitations

- **No runtime test was executed.** Prose only.
- **This flip records a decision; it does not re-verify the implementation.**
  The AppContainer path's behaviour was verified by its own BBF and by the
  repository's real Windows CI job, which is green on the base tree.
- **This flip does not claim the tree is free of further stale claims.** It
  corrects the six sentences it measured, by sweep rather than by inspection:
  the pending-decision class was swept across every tracked `.md` file, and the
  three historical hits are preserved deliberately.
- **The decision's date is 2026-11-17**, the date it was taken. It is recorded
  as a date, not as a commit, because it is a product act rather than a
  repository event.
- **Accepting Decision A generally does not enable anything.** A deployment
  still has to set the flag, stage the parser outside the user profile, be able
  to create the package profile, and accept the residual limitations. That is
  why FU-20 stays open.
