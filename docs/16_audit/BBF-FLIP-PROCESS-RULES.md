# BBF Flip Process Rules

**Status:** Live project policy. Tracked in `sebko23/chess-coach` at `docs/16_audit/BBF-FLIP-PROCESS-RULES.md`.

**Enforcement split.** The mechanical subset of these rules is enforced by
`scripts/dev/verify_bbf_flip_rules.py` (CI job `bbf flip rules verify` in
`.github/workflows/security-audit.yml`, plus a regression test in
`tests/unit/test_verify_bbf_flip_rules.py`). The judgement calls remain policy
enforced by review and by the author's own discipline. Each section below names
which it is.

**Origin.** Recorded from the `chess-coach` flip-9a review cycle on 2026-10-21.
Extended with the platform-skew and fork-verification rules after the PR #175
fork/copy-on-write defect was reproduced on Linux.

---

## 1. Mandatory pre-push verification

Before the first push of a doc-drift flip BBF, run one complete verification
pass against the prospective base tree.

### 1.1 Self-consistency sweep — partially automated

- Compare git-reported numstat with `wc -l` and document trailing-newline
  behavior. *(automated: `--numstat path=add,del`)*
- Verify every self-referential line-count, insertion, deletion, and total
  claim. *(judgement: a count-free phrase is preferred — see §5)*
- Sweep for stale copies of superseded values, including values mentioned in
  prior commit bodies or briefs. *(judgement)*

### 1.2 Git-topology check — automated

- Verify every cited SHA exists in the relevant history and is an ancestor of
  the base. *(automated: `--require-ancestor <sha>`, and every SHA in a
  supplied commit/PR body is checked automatically. SHA extraction requires
  a token to be a 40-character object id, or to contain BOTH a hex letter
  and a digit — so ordinary words such as "defaced" or "deadbeef" are not
  misread as cited SHAs)*
- Distinguish source commits, branch-tip commits, merge commits, and true
  single-parent squash commits. *(judgement, but the ancestry check catches the
  common case of a SHA that never landed)*
- Use terminology that matches the verified topology; do not infer role from
  commit-message wording alone. *(judgement)*

### 1.3 Anchor check — automated

- Re-measure every `path:NNN` citation against the prospective post-merge or
  post-rebase tree. *(automated: `--anchor path:line=substring`)*
- Account for line-count shifts caused by every earlier merged change.
  *(judgement: compute the shift per anchor, never once for the whole brief)*
- Map each citation to the exact content that the surrounding prose asserts,
  then verify semantic containment; **line existence alone is insufficient**.
  *(automated: the anchor spec carries the expected substring, so a line that
  exists but holds different content fails)*
- For cited ranges, verify the range encompasses every item named in the prose
  rather than merely resolving to some text. *(judgement)*
- Resolve each anchor against the tree it describes: pre-patch references
  against the base and post-patch references against the final head.
  *(judgement; the script always resolves `--anchor` against `--head`)*

### 1.4 Preservation check — automated

- Confirm the ledger/product blob and any protected clarification blocks are
  byte-identical to the reviewed form. *(automated: `--preserve
  path:start-end`)*

### 1.5 Scope check — automated

- Confirm only the intended brief and ledger files are staged; exclude source,
  lockfiles, workflows, and unrelated debris. *(automated: `--expect-files`
  asserts the changed-file set exactly)*

---

## 2. Re-run rule

Repeat the full sweep whenever the base branch advances, the branch is
rebased, or any amend changes line counts. A synthetic `git merge-tree` may be
used for a read-only preflight.

---

## 3. Publication rule

Run the self-consistency, topology, and anchor sweeps **before the first push**,
not only after independent review finds a discrepancy. After the final
force-with-lease update, wait for CI and run a bounded independent review of
the final delta.

When a review follows an amend, resolve and pin the final immutable head SHA
before dispatching the reviewer; never review a pre-amend SHA that has already
been superseded.

---

## 4. Platform-skew and fork verification rule

Added after the PR #175 fork/copy-on-write defect was reproduced on Linux.

1. A test skipped or gated off on the developer's platform must be executed on
   its target platform before release. CI may confirm the result, but CI must
   not be the first place the defect is discovered. *(judgement)*
2. A mocked in-process probe is not a substitute for exercising the real
   target-platform path. *(judgement)*
3. In a forked child, mutable parent objects are copy-on-write. A child cannot
   be proven to have mutated a parent-side list, dict, mock, or recorder.
   Assertions about child effects must cross the process boundary through a
   pipe, socket, file descriptor, or exit status, or the child must perform and
   own its assertion. *(judgement)*
4. Fork-sensitive tests must be run repeatedly on the target platform to
   establish determinism. *(judgement)*
5. A wiring test must be mutation-proven: remove or disable the production call
   under test and confirm the test fails for the expected reason. *(judgement)*
6. Resolve and pin the immutable head SHA after the final amend, immediately
   before reviewer dispatch, and again immediately before merge. Abort the merge
   if the head changed unless the new head receives the required review and
   verification. *(judgement: there is no tracked merge-gate script in this
   repository, so the head re-read and the abort decision are the operator's)*

---

## 5. Safety rule

For an already-pushed branch, verify the remote SHA immediately before
rewriting it and use `--force-with-lease`; never use plain `--force`.

---

## 6. Scope discipline for classification

Added after the flip-11 class-based triage of the ledger's `Status: OPEN`
declarations, where a first pass mis-scored 12 of 20 records.

**An entry's status is decided by walking the entry's OWN enumerated scope
list step by step, not by asking whether the artifact the fix was named after
exists in the tree.** One undischarged step means the item is still open.

The two error directions are symmetric and share one root cause — testing
subject existence instead of scope discharge:

- **Wrongly flipping** an entry whose lead is RESOLVED and whose fix shipped,
  but whose enumerated scope still has an open step. This deletes live scope
  from the ledger.
- **Wrongly preserving** a `LOG-ONLY` entry whose deferred subject actually
  shipped. This leaves dead records in the ledger.

Check `git log -- <affected-file>` for the deferred fix, not just the entry's
prose. Full worked examples: `doc-drift-fixup-cycle`'s
`references/class-based-open-status-triage.md`.

---

## 7. Using the enforcement script

Body mode — the CI check. Verifies every SHA cited in a commit body or PR body
exists and is an ancestor of the base:

```bash
python scripts/dev/verify_bbf_flip_rules.py \
  --repo-root . \
  --base "$(git rev-parse origin/main)" \
  --commit-body "$(git log -1 --format=%B HEAD)" \
  --pr-body "$PR_BODY"
```

Manifest mode — the per-flip sweep, before the first push:

```bash
python scripts/dev/verify_bbf_flip_rules.py \
  --repo-root . \
  --base 1aa3808b7aa427bd902b5fcd0abfcee0de55f745 \
  --head 4acdd6da8cf972b0c6648adabc8ed05010e42576 \
  --expect-files docs/16_audit/BBF-doc-drift-flip-12.md docs/16_audit/OPEN-FOLLOWUPS.md \
  --numstat docs/16_audit/BBF-doc-drift-flip-12.md=102,0 docs/16_audit/OPEN-FOLLOWUPS.md=11,11 \
  --require-ancestor ae543ea8 \
  --anchor docs/16_audit/OPEN-FOLLOWUPS.md:1860=RESOLVED \
  --preserve docs/16_audit/OPEN-FOLLOWUPS.md:1664-1664
```

Exit codes: `0` = all requested checks passed, `1` = one or more failed, `2` =
usage or environment error.

---

## 8. What this document does not enforce

Stated plainly, because a gate that looks comprehensive but is not is worse
than no gate:

- Whether a brief's prose is *semantically* true about the code. The anchor
  check proves a cited line holds the content its prose names; it cannot prove
  the prose describes the code correctly. That is the reviewer's job.
- Whether a target-platform test was actually executed on that platform.
- Whether a wiring test is mutation-proven.
- Whether a classification of an open follow-up is correct in substance.

These remain review-time obligations, recorded here so a future session knows
they are not mechanised.

---

## 9. Related

- `scripts/dev/verify_bbf_flip_rules.py` — the enforcement script
- `tests/unit/test_verify_bbf_flip_rules.py` — regression tests, including a
  positive wired-to-CI assertion
- `scripts/dev/verify_commit_refs.py` — the pre-existing `file:line` reference
  gate (complementary: it checks references, this script checks SHAs)
- `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` — authorization
  boundaries referenced by §4
