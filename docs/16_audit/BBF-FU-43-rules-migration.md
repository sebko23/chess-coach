# BBF-FU-43-rules-migration — migrate and enforce the BBF flip process rules

**Sprint intent:** Move the container-only BBF flip verification discipline into the live
repository and wire the mechanically-enforceable subset into CI, so the sweeps that every
doc-drift flip in this project has relied on as author discipline are enforced by a gate
instead of by memory.

**Status:** 6 files. 1 ledger entry (`docs/16_audit/OPEN-FOLLOWUPS.md`, modified), 1 rules
document (`docs/16_audit/BBF-FLIP-PROCESS-RULES.md`, NEW), 1 brief
(`docs/16_audit/BBF-FU-43-rules-migration.md`, NEW), 1 enforcement script
(`scripts/dev/verify_bbf_flip_rules.py`, NEW), 1 regression test
(`tests/unit/test_verify_bbf_flip_rules.py`, NEW), 1 CI workflow
(`.github/workflows/security-audit.yml`, modified — one job added).

**Base:** `main @ 4acdd6da8cf972b0c6648adabc8ed05010e42576`.

---

## §1. Why this exists

`BBF-FLIP-PROCESS-RULES.md` was recorded in the auditor container on 2026-10-21 and lived
there until now. Its own Enforcement-status section said so plainly:

> This copy lives only in the auditor container at
> `/a0/usr/projects/claude_auditor/BBF-FLIP-PROCESS-RULES.md`. It is not tracked in
> `sebko23/chess-coach` and is not enforceable until reviewed, tracked, and wired into the
> live repository's pre-push/pre-merge or CI path.

That is now the only remaining item from the container's rules file. Verified on the frozen
baseline:

```bash
$ git ls-tree -r --name-only 4acdd6da | grep -E 'pre-push|pre-merge'
(no results — neither gate script is tracked on main)
```

The rules describe five sweeps every documentation BBF in this project runs as author
discipline: self-consistency, git-topology, anchor, preservation, scope. None was enforced.
The recurring cost is visible in the project's own record:

| Recurrence | Where |
|---|---|
| A brief claimed an adjacent entry was clean; that entry carried the same defect one line in, with a suffix the grep did not cover | flip-10, caught by leaf review |
| A self-referential anchor count invalidated itself on every edit | flip-10, caught by review-gate |
| A `path:line` citation pointed at a line that existed but held different content | flip-9a, caught by review |
| A PR-body claim ("no stale OPEN line") contradicted the ledger | flip-12, caught by review-gate |

Each was caught — but after the branch was pushed, costing a reviewer round-trip on every
occurrence.

---

## §2. Scope decision: mechanical subset only

The rules file mixes two kinds of obligation. Conflating them would produce a gate that
looks comprehensive and is not, which is worse than no gate.

**Automated** (deterministic, checkable against the tree):

| Rule | Enforcement |
|---|---|
| Cited SHA exists and is an ancestor of the base | `--require-ancestor`, plus every SHA in a supplied body |
| Changed-file set equals the expected set | `--expect-files` |
| Per-file numstat matches the claim | `--numstat path=add,del` |
| Anchor holds the content its prose claims | `--anchor path:line=substring` |
| Protected ranges byte-identical base vs head | `--preserve path:start-end` |

**Judgement** (not mechanically checkable): whether a brief's prose is semantically true
about the code; whether a target-platform test was executed on that platform; whether a
wiring test is mutation-proven; whether an open follow-up's classification is correct in
substance.

§8 of the rules document states the judgement set explicitly, so a future session knows
what the gate does **not** cover.

### What the script adds that the repo does not already have

`scripts/dev/verify_commit_refs.py` (existing, wired as CI job `commit ref verify`) validates
`file:line` references in a commit body or PR body. It does **not** validate cited SHAs.
A body can name a plausible-looking 7-hex token that was never committed, or one that never
landed on `main`, and the reference gate stays green.

That is the gap this BBF closes, and it is why the CI job is a new job rather than a flag
on the existing one.

---

## §3. The three layers

The repo already uses a three-layer shape for policy checks
(`scripts/dev/verify_commit_refs.py` + `tests/unit/test_verify_commit_refs.py` + a
`security-audit.yml` job). This BBF follows it.

### Layer 1 — the rules document

`docs/16_audit/BBF-FLIP-PROCESS-RULES.md`. Adapted for repo ownership: the container-only
Enforcement-status section is replaced with a description of the enforcement split, and
every section names whether it is automated or judgement.

### Layer 2 — the script

`scripts/dev/verify_bbf_flip_rules.py`. Two modes:

- **Body mode** — the CI check. Extracts every SHA-like token from a supplied commit body
  and PR body, requires each to exist and be an ancestor of the base. This is the
  universally-applicable check.
- **Manifest mode** — the per-flip pre-push sweep. Asserts scope, numstat, anchors, and
  preservation ranges against a base/head pair.

Exit codes: `0` = all requested checks passed, `1` = one or more failed, `2` = usage or
environment error.

SHA extraction filters ordinary prose: a token must be a full 40-character object id, or
contain BOTH a hex letter and a digit. Requiring a digit is what keeps English words made
only of the letters a-f ("defaced", "deadbeef", "cafebabe") from being read as cited SHAs.

### Layer 3 — the test and the CI job

`tests/unit/test_verify_bbf_flip_rules.py` — 14 tests covering each check's accept and
reject paths, plus two positive wired-to-CI assertions.

CI job `bbf flip rules verify (SHA ancestry)` in `.github/workflows/security-audit.yml`.
On a PR the base is `${{ github.event.pull_request.base.sha }}` and the commit body is read
from `${{ github.event.pull_request.head.sha }}` — NOT from `git log -1 HEAD`, which on a
`pull_request` event is GitHub's synthetic merge commit. On a push to `main` the base is
`HEAD~1` (the parent of the commit being pushed). The job uses `fetch-depth: 0` so the
ancestry check has the full history.

---

## §4. Verification performed

### Tests

```
14 passed in 6.31s
```

### Negative tests (the meta-test must fail closed)

Per the `test-design-positive-wired-assertions` skill, a meta-test that passes on the
current state is necessary but not sufficient — it must also fail when its condition is
violated.

| Mutation | Expected | Result |
|---|---|---|
| `verify_bbf_flip_rules.py` reference removed from `security-audit.yml` | wired-to-workflow test FAILS | ✅ exit 1, `test_rule_script_is_referenced_by_a_ci_workflow` FAILED |
| SHA-ancestry check neutered in the production script | non-ancestor test FAILS | ✅ exit 1, `test_non_ancestor_sha_is_rejected` FAILED |

Both mutations were reverted and the suite re-verified green. The working tree was
confirmed byte-identical to its pre-negative-test state after each restore.

### Real-world exercise against a shipped flip

The script was run against flip-12's actual squash-merged commit (`4acdd6da`, base `1aa3808b`) — a real
BBF with real scope, numstat, anchors, and preservation requirements:

| Invocation | Expected | Result |
|---|---|---|
| Real scope + numstat + anchors + preservation | exit 0 | ✅ `OK: BBF flip rules verified (scope (2 expected file(s)); numstat (2 spec(s)); anchors (1 spec(s)); preservation (1 spec(s)))` |
| Wrong numstat claim (`11,12` vs actual `11,11`) | exit 1 | ✅ `numstat mismatch for docs/16_audit/OPEN-FOLLOWUPS.md: expected 11/12, actual 11/11` |
| Anchor at the right line but the wrong content | exit 1 | ✅ `anchor docs/16_audit/OPEN-FOLLOWUPS.md:1860 does not contain 'heavy-lift caveat applies'` |
| Preservation range over a changed line | exit 1 | ✅ `preserve range docs/16_audit/OPEN-FOLLOWUPS.md:1860-1860 changed between 1aa3808b and 4acdd6da` |
| Body mode against flip-12's merged commit body | exit 0 | ✅ `OK: BBF flip rules verified (sha-ancestry (11 SHA(s)))` |

The third case is the one that matters most: an anchor at a line that **exists** but holds
different content fails. That is the flip-10 defect class, and an existence-only check
would have passed it.

### Workflow

The modified `security-audit.yml` parses as valid YAML with 6 jobs:
`pip-audit`, `gitleaks`, `uv-lock-check`, `commit-refs-verify`, `bbf-flip-rules-verify`,
`pnpm-audit`.

### Diff

Staged numstat at the time of writing:

```
  60    1  .github/workflows/security-audit.yml
 211    0  docs/16_audit/BBF-FLIP-PROCESS-RULES.md
 245    0  docs/16_audit/BBF-FU-43-rules-migration.md
  70    0  docs/16_audit/OPEN-FOLLOWUPS.md
 424    0  scripts/dev/verify_bbf_flip_rules.py
 491    0  tests/unit/test_verify_bbf_flip_rules.py
```

6 files changed, +1501 insertions(+), 1 deletion(-). The single deletion is the workflow's
`# Job 5: pnpm-audit` comment, renumbered to `# Job 6:` when the new job was inserted
above it.

The ledger grows from 3139 to 3209 lines (the FU-43 entry is 70 lines). The trailing
newline is preserved and the diff carries no end-of-file marker.

---

## §5. What this BBF does not do

- It does not retro-apply the rules to the flips already shipped.
- It does not automate the platform-skew or fork-verification rules. Those need a
  cross-platform test-runner; a separate workstream.
- It does not restore `scripts/pre-push-gate.sh` / `scripts/pre-merge-gate.sh`. The October
  handoff references them as having existed; they are not tracked on `main` and were never
  adopted. The CI-job shape already in use covers the same ground, and reviving two
  untracked shell scripts would add a second, weaker enforcement path.
- It does not touch any FU's status. FU-43 is the only ledger entry, and it is RESOLVED by
  this BBF.

---

## §5a. Leaf-review response (2026-10-24)

The independent leaf review returned **NEEDS CHANGES** with two CI-breaking blockers and
several numeric errors. Each was verified independently against the committed tree before
acting, and each was confirmed real.

| Finding | Verdict | Fix |
|---|---|---|
| **B1** — the CI job read the commit body from `git log -1 HEAD`, which on a `pull_request` event is GitHub's synthetic merge commit (`Merge <head> into <base>`). The head SHA in that message was then checked as a cited SHA against a base it is by definition not an ancestor of, so the job would fail on its own PR. | CONFIRMED | The job now reads the body from `${{ github.event.pull_request.head.sha }}` and uses `${{ github.event.pull_request.base.sha }}` as the base. |
| **B2** — the new test file depended on `origin/main` and `HEAD~1`, but `smoke.yml` checks out at depth 1, where neither resolves. 5 of the new tests failed under a faithful depth-1 clone. | CONFIRMED | Every git-history-dependent test now skips when the history is unavailable. Verified: 14 passed inside a real depth-1 clone. |
| Commit body said `+1409 / -1` and `458 lines` | CONFIRMED | Corrected to the figures at the time of writing. |
| Brief numstat table said `195   0` for the brief | CONFIRMED | Corrected. |
| Brief cited `599161a7` (flip-12's PR head) — reachable from no ref, and absent from a fresh clone | CONFIRMED | Both documents now cite `4acdd6da`, the squash-merged commit with an identical tree, which IS an ancestor of `main`. |
| Brief's grep transcript used `pre-push\|pre-merge\|gate`, which matches 40 paths (via "gateway") | CONFIRMED | Narrowed to `pre-push\|pre-merge`, which matches 0. |
| Rules doc §7 example was not copy-paste runnable (exit 1) | CONFIRMED | Rewritten against the merged commit; it now exits 0. |
| SHA extraction flagged hex-letter English words (`defaced`, `deadbeef`, `cafebabe`) | CONFIRMED | The filter now requires a hex letter AND a digit, or a full 40-char object id. |
| `--expect-files` with an empty list was a vacuous pass | CONFIRMED | An empty expectation set is now an error. |
| Script docstring claimed `core.autocrlf=true`; the repo sets `false` | CONFIRMED | Corrected. |
| Rules doc §4.6 claimed "the merge gate checks the head SHA"; no merge-gate script is tracked | CONFIRMED | Reworded to say the re-read and abort decision are the operator's. |

The rules-doc §7 example and the brief's transcript rows were regenerated against the merged
commit, so the quoted output is what the tool actually prints.

---

## §6. Cross-references

- `docs/16_audit/BBF-FLIP-PROCESS-RULES.md` — the rules, now tracked.
- `scripts/dev/verify_bbf_flip_rules.py` — the enforcement script.
- `tests/unit/test_verify_bbf_flip_rules.py` — regression tests + wired assertions.
- `scripts/dev/verify_commit_refs.py` — the pre-existing `file:line` gate (complementary).
- `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` §7.1 — the
  destructive-operation rule the flip rules reference.
- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-43 — the ledger entry.
