# BBF-doc-drift-flip-14 — correct the FU-5 and FU-6 stale status declarations

**Sprint intent:** FU-5's and FU-6's stale `**Status:**` declarations still
read as current-state assertions, so a casual ledger-grep reports them as
`IN PROGRESS` and `OPEN` even though both implementations shipped months ago
and each entry already carries a `**Status (clarified ...)**` block saying
RESOLVED. This flip replaces each stale declaration with a one-line pointer
to the entry's existing canonical resolution, following the shape flip-12
landed for the same class of defect.

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified,
`docs/16_audit/BBF-doc-drift-flip-14.md` NEW per-flip brief).

**Base:** `main @ db707fe2432f83eb28dc22f0284de7912d04ceb1` (the PR #194 squash merge).

**Sibling flips:** flip-12 (11 stale statuses, PR #177) and flip-13 (FU-38,
PR #182). flip-11 was never published. flip-8 (2026-10-20) is the flip that
prepended the `Status (clarified ...)` blocks these two entries carry today.

---

## §1. Why this flip exists

Doc-drift flip-8 prepended a `**Status (clarified 2026-10-20, doc-drift
flip-8):** RESOLVED` block to both entries, deliberately preserving the prior
headline lines as historical context. What it did not do was stop those
headline lines from reading as current-state assertions, so the ledger
still carries two declarations that assert a live status the work has long
since discharged.

flip-12 later swept the ledger for stale mid-entry declarations and fixed
eleven of them. It did not consider FU-5 or FU-6: its scope table lists the
eleven entries it classified, and neither FU-5 nor FU-6 appears in it. The
two survived because flip-8 had already given them a clarified block, so the
"stale mid-entry OPEN declaration" test flip-12 used did not select them --
even though each entry still carries the original stale declaration.

These are the only two entries in the ledger whose plain `**Status:**`
line asserts an UNRESOLVED state while the same entry's live clarified
marker says RESOLVED -- the only entries where the plain declaration
contradicts the entry's own live status.

The class is narrower than "carries both markers". Seven entries carry both
a clarified block and a plain `**Status:**` line (FU-5, FU-6, FU-7, FU-15,
FU-17, FU-21, FU-38), but the other five entries' plain lines already say
RESOLVED, so they assert nothing contradictory. FU-7's two plain lines say
PARTIAL and OPEN, and both are truthful: FU-7's own scope retains the full
`.bin` import/export surface beyond the alpha-ext shape, so its unresolved
declarations describe genuinely open work. This flip does not touch them.

## §2. The scope-discharge test (docs/16_audit/BBF-FLIP-PROCESS-RULES.md §6)

Per §6, an entry's status is decided by walking the entry's own enumerated
scope list step by step, not by asking whether the named artifact exists.
Both entries' scopes are fully discharged:

FU-5's "Implementation sketch (when picked up)" offers three alternatives; the
adopted one shipped in full. The server-side helper exists as
`_pv_to_san()` in `services/chess_coach/narration/pipeline.py`, the narration
route populates `pv_moves_san` on the response, the protocol type declares
`pv_moves_san` alongside the authoritative UCI `pv_moves`, the frontend reads
`pv_moves_san ?? pv_moves` in `CoachPanel.tsx`, which passes the resolved
value down to `SuggestionList` as its `pvMoves` prop, and the regenerated
`apps/desktop/src/services/coach/api.ts` carries the new optional field.

(The ledger's preserved historical prose at that entry names
`SuggestionList.tsx` as also carrying the `??` chain. That attribution is not
accurate -- `SuggestionList.tsx` holds no `pv_moves_san` reference -- but the
prose line is byte-identical to the base tree and is out of scope here,
because preserving the superseded wording verbatim is the point of this
flip. This brief states the measured behaviour instead. Squash `cada4ab2` (PR #81) is an ancestor of `main`.

FU-6's "Fix options (when picked up)" offers three alternatives; option (a)
shipped. `app.state.engine_pool = MagicMock()` is set in all three fixture
blocks in `tests/integration/test_narrative_position_fk.py`, each carrying a
`# FU-6:` comment. Squash `e091988c` (PR #82) is an ancestor of `main`. The
three tests pass, as does the FU-5 companion suite
`tests/integration/test_narration_pv_moves_san.py`.

Both cited squashes are ancestors of the base tree, so both may be cited in
the corrected declarations under the SHA-ancestry rule.

## §3. The replacement shape

Per the flip-shape rule in `doc-drift-fixup-cycle`, a clarification block must
be UNIQUE per entry: when an entry already has one, do not prepend a second,
because two blocks both claiming to be the live marker breaks the
byte-identical invariant at the meta-level even though both survive verbatim.
Both FU-5 and FU-6 already carry a clarified block, so this flip REPLACES the
stale declaration with a one-line pointer to that block, in the shape flip-12
landed:

```text
**Status:** RESOLVED <date> via squash `<sha>` (PR #N, <what shipped>); see the canonical resolution above. Historical context preserved below:
```

FU-5's stale declaration is ten lines, and its trailing nine lines are the
historical prose. Following flip-12's shape, only the first line is replaced
and the pointer's tail preserves the original line's continuation, so the
remaining nine lines stay byte-identical and every historical fact survives --
including the codegen target and the protocol spec citation, which a
rewritten block would have dropped.

The two `**Status (clarified ...)**` blocks are byte-identical before and
after. Nothing else in the ledger changed.

## §4. Line-count neutrality is load-bearing here

PR #194 landed ten `**Original entry:** lines N-M` pointers in this same
ledger. Their VALUES are line numbers, and every one of the ten targets sits
below this flip's edit region. Any net line-count change here would shift
all ten pointer values and re-introduce the stale-pointer defect PR #194 was
merged to fix -- a defect that no CI gate catches, because nothing in this
repository validates line-number citations.

This flip is therefore line-count neutral: FU-5's declaration is replaced
one line for one line, and FU-6's likewise. The ledger's line count is
unchanged, and all ten pointer values still resolve to their entries'
headings with their Rule-B extents intact.

## §5. Verification

- Exactly two ledger lines changed: L206 and L339. Every other line is
  byte-identical to the base tree.
- Line-count neutral: the ledger measures the same number of lines before and
  after.
- All 10 of 10 `**Original entry:**` pointer values still
  resolve to the heading of the FU entry they name, with the correct Rule-B
  extent.
- Both `**Status (clarified ...)**` blocks are byte-identical before and
  after.
- The stale declarations `**Status:** **IN PROGRESS 2026-08-06**` and
  `**Status:** OPEN. Low urgency. Not blocking. Pick up after FU-5 ships.` are
  gone as current-state assertions.
- Every historical fact from the superseded declarations survives verbatim,
  including the branch name, the base commit, the helper's behaviour, the
  frontend fallback chain, the codegen target, and the protocol spec
  citation.
- The FU-5 and FU-6 implementations are present on the base tree and their
  cited squashes are ancestors of it.
- `tests/integration/test_narrative_position_fk.py`: 4 passed.
  `tests/integration/test_narration_pv_moves_san.py`: 4 passed.
- `git diff --check` clean; `verify_commit_refs.py` and
  `verify_bbf_flip_rules.py` pass against the commit body and the PR body.
- Scope: 2 2 docs/16_audit/OPEN-FOLLOWUPS.md plus this brief.

## §6. Explicit exclusions

This flip does not touch:

- **FU-2**, whose `PARTIALLY RESOLVED` status names FU-5 as its deferred
  part. That status shape is intentionally preserved, exactly as flip-8
  recorded it: FU-2's docstring fix is resolved and the FU-5 deferral is
  named as its remaining part.
- **FU-7**, whose plain `**Status:**` lines also read PARTIAL and OPEN.
  They are not stale: FU-7's own scope retains the full `.bin`
  import/export surface beyond the alpha-ext shape, so both declarations
  describe genuinely open work and are left exactly as they are.
- **FU-15, FU-17, FU-21 and FU-38**, whose plain `**Status:**` lines
  already say RESOLVED and therefore contradict nothing. FU-15 does have a
  ledger entry; it is named here because it carries both marker kinds, and
  it is excluded because its plain line asserts no contradiction.
- **FU-42**, which older flip briefs name as open and which does have a
  ledger entry. Its scope is the A-F11 sandbox-isolation test follow-on to
  FU-19, which is a separate work item, so it is not in scope here.
- **Any other ledger entry, source file, test, workflow, or configuration.**

## §7. Honest limitations

- This flip changes no behaviour and closes no functional gap. Both
  implementations had already shipped; only the ledger's summary of them
  was wrong.
- The flip does not mark FU-20 or any other entry resolved. FU-20's status
  and the FU-5/FU-6 status are independent records.
- The corrected declarations cite the squashes that shipped the work
  (`cada4ab2`, `e091988c`). It does not claim they are the commits that
  introduced the ledger defect -- the 2026-08-10 doc-drift fix-ups did that,
  and their append blocks are preserved unchanged below.
