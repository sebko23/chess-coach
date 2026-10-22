# BBF-doc-drift-flip-9c — correct FU-19 + FU-42 stale status lines in OPEN-FOLLOWUPS.md

**Sprint intent:** Correct two stale `**Status:** OPEN` lines in `docs/16_audit/OPEN-FOLLOWUPS.md` — one in the FU-19 entry, one in the FU-42 entry — both of which describe work that shipped on 2026-10-16 via PR #143.

This is the **9c flip**, sibling to flip-9a (FU-15) and flip-9b (FU-17). Like those, it closes already-landed work and touches no implementation.

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified, `docs/16_audit/BBF-doc-drift-flip-9c.md` NEW per-flip brief).

---

## §1. What shipped (live evidence)

The A-F11 sandbox-isolation test work identified by FU-19 and tracked for closure by FU-42 landed 2026-10-16:

- **Canonical squash-merge:** `7d51afa0` — *"Merge pull request #143 from sebko23/bbf-fu19-a-f11-sandbox-tests"*, author `Sebastian Wasielewski <lesson@o2.pl>`, committed 2026-10-16T08:51:31+02:00. Confirmed present on `origin/main` via `git branch -r --contains 7d51afa0`.
- **Branch-tip evidence:** `826b1979` — *"test(security): BBF-FU-19-A-F11-sandbox-tests — add 4 A-F11 sandbox-isolation tests to `tests/unit/test_pdf_ingest_security.py`"*, author `Hermes Agent <hermes@nousresearch.com>`, 2026-10-16T08:39:40+02:00. Also on `origin/main`.
- **Brief file:** `docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md` (6947 bytes, git-tracked, on `origin/main`).
- **Test file:** `tests/unit/test_pdf_ingest_security.py` (23572 bytes, git-tracked, on `origin/main`), section E "A-F11 sandbox isolation properties (FU-19, 2026-10-16)" at L315.

`7d51afa0` is the SHA cited in the status lines (canonical merge, matching every prior flip's citation convention). `826b1979` is cited in FU-42's Resolution-BBF line explicitly labelled as branch-tip evidence, because it is the commit that authored the brief file.

---

## §2. The two corrections (final shape on `main`)

### §2.1 FU-19 — mid-entry stale status (minimal replacement)

Pre-patch L1605–L1606 (identical in base and post-patch; the swap is 2→2):

```
**Status:** OPEN. Real contract gap, no external blocker. Logged
for record-keeping per the directive. Investigation-first BBF would:
```

Post-patch L1605–L1606:

```
**Status:** RESOLVED 2026-10-16 via PR #143 (`7d51afa0`); see the RESOLVED block above. Historical investigation plan preserved below.
Investigation-first BBF would:
```

**Why minimal rather than full replacement.** The stale block bundled the `OPEN` status with a 5-step numbered investigation plan (steps 1–5, L1607–L1616, unchanged by this flip). FU-19's own RESOLVED block declares that plan's work complete, so the plan is now historical. Deleting it would remove the audit trail of *how* the gap was to be closed. This flip therefore replaces only the status opening and retains the plan byte-identical. The trailing clause "Historical investigation plan preserved below" exists so a reader landing on the plan does not mistake it for a live TODO — that clause is the reason the plan can stay without reintroducing the stale-status ambiguity this flip corrects.

Ledger delta: `+2 / −2` (2 lines in, 2 lines out; net 0).

### §2.2 FU-42 — stale status (2-line swap)

Pre-patch L3021–L3023:

```
**Status:** OPEN. Resolution BBF:
`docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md`.
```

Post-patch L3021–L3022:

```
**Status:** RESOLVED 2026-10-16 via PR #143 (`7d51afa0`). Resolution BBF:
`docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md` (branch-tip commit `826b1979`).
```

Ledger delta: `+2 / −2`.

---

## §3. Preserved byte-identical

**FU-19:**
- heading L1574;
- the existing `**Status:** **RESOLVED 2026-10-16 via squash-merge of PR #143**` block (L1576–L1584);
- identified/gap prose (L1586–L1603);
- `Investigation-first BBF would:` + the 5-step plan (L1606–L1616);
- "Why this is FU-19" section and cross-references (L1618 onward).

**FU-42:**
- heading L2987;
- the 5-property enforced/tested table (L2994–L3000);
- the 4-test table (L3010–L3015, all four test rows);
- the skip-rationale prose (L3017–L3019);
- the out-of-scope list (L3024 onward) and cross-references.

Verified by direct `diff` of `git show origin/main:docs/16_audit/OPEN-FOLLOWUPS.md` ranges against the corresponding post-patch ranges: the only differing lines in the FU-19 window are L1605–L1606, and the only differing lines in the FU-42 window are L3021–L3022.

---

## §4. What this BBF does NOT do

- **Does not touch any test file.** In particular it does not edit the three skip markers in `tests/unit/test_pdf_ingest_security.py`.
- **Does not edit FU-19's RESOLVED block** (L1576–L1584), which already carried the correct status before this flip.
- **Does not delete the 5-step investigation plan.**
- **Does not change any implementation.** `services/chess_coach/pdf_ocr/subprocess_runner.py` is untouched.
- **Does not correct FU-42's own test tables** (L3013, L3015) even though they carry a FU-numbering error — see §5.
- **Does not touch FU-20, FU-21, FU-22** ledger entries.

---

## §5. Recorded follow-up (deliberately outside this BBF)

Investigation during this BBF found a **stale skip reason and a FU-numbering error in test code**, left unchanged here because it is a test-code change, not a documentation change:

`tests/unit/test_pdf_ingest_security.py` → `test_subprocess_cannot_initiate_outbound_network` (L404) carries a `pytest.mark.skip` whose reason states the property is "NOT enforced today" and directs the reader to **FU-22**. Live inspection of `services/chess_coach/pdf_ocr/subprocess_runner.py` shows:

- `set_network_isolation_preexec()` is implemented at L128 (Linux: `os.setsid()` then `unshare(CLONE_NEWNET)` via ctypes at L206–244; Windows: best-effort proxy-env strip);
- it is composed into the child's `preexec_fn` at L602 alongside `set_rlimit_as_preexec(...)()` at L601 and `set_fs_isolation_preexec(tmpdir)()` at L603;
- the canonical ledger entry for network isolation is **FU-20**, whose status reads `PARTIALLY RESOLVED 2026-10-18` via PRs #163/#164 — **not FU-22**, which is the 2 GB memory cap.

FU-42's own tables repeat the same numbering error (L3013 attributes the network test to FU-22; L3015 attributes the memory test to FU-20, inverting the correct mapping). Correcting the skip reason and the two table cells requires editing test code and ledger prose in one change; per the one-BBF-one-clean-change rule this is deferred to a separate test-code BBF.

Two related observations from the same investigation, also recorded rather than acted on:

- The filesystem skip (L455) is **correctly capability-gated**: its reason already describes the bind-mount path implemented per BBF-FU-21-bind-mount and defers the negative assertion to environments with `CAP_SYS_ADMIN` / `unprivileged_userns_clone`.
- The memory skip (L488) carries an `assert True` placeholder; real coverage for the mechanism already exists in `tests/unit/test_subprocess_runner.py`, which imports all three isolation callables (L32–34).

---

## §6. Verifications (live, this session)

- Base: **rebased onto `main @ e7c2a11a93603511d87f243cb18d8d73abefca4d`** (PR #173 merge commit) before publication. Authoring base was `main @ 12d4962e` (PR #171 merge commit). PRs #172 (`7ffe9f1c`, −1 net ledger line) and #173 (`e7c2a11a`, −4 net ledger lines) landed above FU-19 in the interim, so every FU-19/FU-42 anchor in this brief is numbered against the post-#173 tree (−5 from the authoring-base numbering). `git rev-parse --verify bbf-doc-drift-flip-9c` did not exist beforehand; branch created from `main` with a clean tree.
- `git show 7d51afa0 --no-patch --format='%H %an <%ae> %aI %s'` → author `Sebastian Wasielewski <lesson@o2.pl>`, 2026-10-16T08:51:31+02:00. Topology: `7d51afa0` is a **2-parent merge** for PR #143 (parents `e61db21e` + `826b1979`); `826b1979` is its **single-parent branch-tip** source commit. `3f3610be` (PR #93) and `ddeb1e37` (PR #91) are also **2-parent merges**, not squashes; `12d4962e` (PR #171) is the true single-parent squash in this chain.
- `git show 826b1979 --no-patch --format='%H %an <%ae> %aI %s'` → author `Hermes Agent <hermes@nousresearch.com>`, 2026-10-16T08:39:40+02:00.
- `git branch -r --contains 7d51afa0` → includes `origin/main`.
- `git diff --numstat` (ledger) → `4 4 docs/16_audit/OPEN-FOLLOWUPS.md`.
- `wc -l docs/16_audit/OPEN-FOLLOWUPS.md` → `3138`, identical to `main @ e7c2a11a` (both corrections are line-count-neutral: each is a 2-line → 2-line swap, so the ledger neither grows nor shrinks).
- `git show origin/main:…OPEN-FOLLOWUPS.md | sed -n '1601,1616p'` diffed against post-patch `sed -n '1601,1616p'` → only L1605–L1606 differ (the status lines); `Investigation-first BBF would:` and steps 1–5 are identical.
- FU-42 window diff (L2983–L3023) → only L3021–L3022 differ (the status lines).
- No tracked file outside `docs/16_audit/` modified. No `??` debris staged.
- Trailing-newline behaviour: this brief has **no final newline** (last byte is `.`). `wc -l` therefore reports one fewer line than git's numstat for this file. Reviewers must read git's `--numstat` output, not `wc -l`, when reconciling the brief's self-reported totals.

Pre-commit hygiene:

- Fresh branch, zero prior commits at branch creation.
- Author and Committer both forced via `git -c user.name='Sebastian Wasielewski' -c user.email='lesson@o2.pl'`.
- No force operations.

---

## §7. Cross-references

- `docs/16_audit/BBF-doc-drift-flip-9a.md` (flip-9a, `dd91d97f`) — FU-15 headline replacement.
- `docs/16_audit/BBF-doc-drift-flip-9b.md` (flip-9b, `1aa3820d`) — FU-17 mid-entry `Status: OPEN` replacement; the structural precedent for flip-9c's FU-19 hunk.
- `docs/08_security/security-strategy.md` §A-F11 — the canonical 5-property contract.
- `docs/02_modules/module-decomposition.md` §A-F7 — the subprocess sandbox spec.
- `services/chess_coach/pdf_ocr/subprocess_runner.py` — the three isolation callables (`set_rlimit_as_preexec` L64, `set_network_isolation_preexec` L128, `set_fs_isolation_preexec` L283) and their composition at L601–603.
- `tests/unit/test_pdf_ingest_security.py` — section E (L315) and the three skip markers discussed in §5.
- `docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md` — the resolution brief shipped by PR #143.

---

## §8. Pre-leaf-review checklist (for the next session's reviewer)

1. **Numstat:** `git diff --numstat origin/main..HEAD` should show **2 files changed**, ledger at **`4 4`** and the brief at its own measured line count (read it with `git diff --cached --numstat`, not `wc -l` — see the flip-9b no-trailing-newline lesson).
2. **Status coherence:** FU-19 L1605 and FU-42 L3021 both begin `**Status:** RESOLVED 2026-10-16 via PR #143`; `grep "Status: OPEN"` no longer matches inside either entry. FU-19's separate L1576 RESOLVED block is unchanged.
3. **Preservation:** FU-19's 5-step plan and its L1576–L1584 RESOLVED block are byte-identical to `main`; FU-42's two tables and out-of-scope list are byte-identical. Verify with `git diff main -- docs/16_audit/OPEN-FOLLOWUPS.md` showing exactly two 2-line hunks.
4. **Citation accuracy:** `7d51afa0` resolves to the PR #143 merge on `origin/main`; `826b1979` is labelled branch-tip in the ledger text itself.
5. **Scope discipline:** §4 lists what flip-9c does NOT do; §5 records the deferred test-code follow-up. No test file appears in the diff.
6. **Pre-PR cross-reference verification (v0.7.124):** every `path:NNN` and SHA above resolves against the live tree.
7. **Identity:** Author and Committer are both `Sebastian Wasielewski <lesson@o2.pl>`.