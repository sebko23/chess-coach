# BBF-FU-29-scoping-brief — ratchet strategy for ruff, mypy, and pytest-cov

**Sprint intent:** Establish a ratchet strategy for the 3 quality
tools declared in `pyproject.toml`'s `[dev]` extras but never
invoked in CI (per the FU-29 ledger entry, 2026-08-25 state
check). This is the **burn-down-first, then-wire** path the
ledger entry explicitly calls out as the non-naive approach.

**Status:** Doc-only BBF. No code, no config, no CI change.
This BBF ships the ratchet **strategy**; the ratchet
**implementation** is a follow-up BBF (or series of BBFs)
per §2 below.

## §1. The current state (2026-10-16, this BBF)

| Tool | Declared? | Configured? | Invoked in CI? | Backlog (2026-08-25) |
|---|---|---|---|---|
| `ruff` | ✓ (`pyproject.toml:59`) | ✓ (`[tool.ruff]` block, 12 lines) | ✗ | 2,694 findings |
| `mypy` | ✓ (`pyproject.toml:60`) | ✓ (`[tool.mypy]` block, strict=true) | ✗ | 154 errors / 31 files |
| `pytest-cov` | ✓ (`pyproject.toml:58`) | ✓ (`[tool.coverage.run]` + `[tool.coverage.report]`) | ✗ | no floor exists |

(The FU-29 ledger entry also flags 146 of the 2,694 ruff findings
as auto-fixable, and the top classes as E501×185, S607×77, Q1/Q2/Q3×~194,
S310×70.)

**Verified this session:** the only `coverage` reference in
`.github/workflows/` is the **i18n key coverage** check in the
desktop frontend lint job (line 114 of `smoke.yml` — unrelated
to Python pytest-cov). The only `ruff` references in `scripts/`
are `# ruff: noqa` suppressions, not invocations. **No invocation
of any of the 3 tools exists anywhere in CI or scripts.**

**Two existing gaps beyond the FU-29 entry:**

1. **`tmp_*.py` files leak into the repo root.** The ledger
   entry's operational footnote says: "mypy aborted on
   untracked `tmp_find_actual_target.py` before any project
   file was checked. Run these tools against `services/`
   (and consider a scoped ignore) until the audit layer
   gets its own exclusion convention." As of 2026-10-16,
   **131 untracked `tmp_*.py` files** exist in the repo
   root (the standing-audit scratch files). This is a
   pre-condition for any of the 3 tools to run cleanly.
   The fix is a 1-line `.gitignore` addition:
   `tmp_*.py` (covers `tmp_*.py` and `tmp_*.py.bak`).
   That is **out of scope** for this BBF (the brief is
   about ratchet strategy, not a `.gitignore` fix) but
   is a pre-condition for §2 below.

2. **The configs are aspirational.** `[tool.mypy] strict = true`
   means "all 154 errors are violations of the configured
   rules." Naively wiring `mypy --strict` to CI produces a
   permanently-red gate. The ratchet below is the only
   honest path.

## §2. The ratchet strategy (proposed)

The ratchet has 3 stages. Each stage produces a discrete
artifact; each stage can be a separate BBF (or sub-PR in
a multi-BBF series).

### Stage 1: Burn-down the existing backlog (no CI change)

**Goal:** reduce the backlog to a "manageable" size without
flipping any CI state to "red."

**Tool-by-tool:**

| Tool | Burn-down approach | Est. effort | Acceptance criterion |
|---|---|---|---|
| **ruff** | `ruff check . --fix` to apply the 146 auto-fixable findings; manual pass for the remaining 2,548 (style-dominated, top 4 classes cover ~526). | ~2-3 hrs | 0 ruff findings (or threshold-based) |
| **mypy** | `mypy --install-types --non-interactive services/ libs/ apps/cli/` to install missing stubs (the `[[tool.mypy.overrides]]` for `chess.*` is `ignore_missing_imports = true` but not all imports are `chess.*`); manual fix for remaining errors. | ~2-4 hrs | 0 mypy errors (or threshold-based) |
| **pytest-cov** | No backlog to burn — the tool never ran, so there's nothing to "fix." | ~10 min | Just-in-time when the CI gate goes in (Stage 3). |

**Key insight:** Stage 1 does NOT introduce a CI gate. It
just runs the tools locally and makes the codebase conform
to the existing configs. The repo's local pre-push gate
(cf. `scripts/dev/`) can grow to include a "warnings only"
invocation as a transition step.

### Stage 2: Baseline-and-no-regressions ratchet (no CI gate flip yet)

**Goal:** introduce the "ratchet" — the system fails on new
findings but tolerates existing ones — without flipping
the gate to "red."

**Tool-by-tool:**

| Tool | Ratchet mechanism |
|---|---|
| **ruff** | `ruff check . --output-format=concise --exit-zero > /tmp/current.txt; diff /tmp/ruff-baseline.txt /tmp/current.txt; exit $?` — fails only on new findings. The baseline file is committed. |
| **mypy** | Same pattern: capture `mypy --strict services/ libs/ apps/cli/ --output=json` to a baseline JSON, fail on new errors. |
| **pytest-cov** | Threshold-based: start with the current coverage (whatever it is, likely <10%) and ratchet up by 5% per release. |

**Key insight:** Stage 2 is "warn-then-fail" — the CI
invocation runs the tools, the ratchet compares to the
baseline, and the gate flips red only on new findings.
This is the only honest path to a green CI gate.

### Stage 3: Wire to CI (the actual "fix")

**Goal:** add the ratchet invocations to the existing
`smoke.yml` (or a new `quality.yml` workflow).

**Mechanically:** the ratchet commands from Stage 2 become
3 new `run:` steps in `smoke.yml` (or a new workflow). The
baseline files (`ruff-baseline.txt`, `mypy-baseline.json`,
`coverage-baseline.json`) are committed in the same PR.

**Key insight:** Stage 3 is the "wire the gate" step the
ledger entry warns against doing naively. The combination
of Stages 1+2+3 is the full ratchet — without Stages 1
and 2, Stage 3 produces a permanently-red gate.

## §3. The burn-down order (per the FU-29 ledger entry's hint)

The ledger entry says: "any future scoping brief needs a
config-tuning/ratchet strategy (e.g. baseline-and-no-regressions)
before enforcement talk." This is the explicit ask.

The recommended order is **lightest-to-heaviest**:

1. **pytest-cov first** (lightest — no backlog, just a
   coverage-baseline file + a `coverage report` step in
   CI). Estimated BBF: 30-60 min, single PR.
2. **ruff second** (medium — 2,694 findings, but 146
   auto-fixable and the top 4 classes are
   mechanical). Estimated BBF: 2-3 hrs burn-down, then
   30-60 min for the ratchet + CI wire. 2-3 PRs.
3. **mypy last** (heaviest — 154 errors across 31 files,
   strict mode is aspirational, and the
   `chess.*` overrides suggest there are upstream library
   type issues to work around). Estimated BBF: 2-4 hrs
   burn-down + stubs installation, then 30-60 min for
   the ratchet + CI wire. 2-3 PRs.

**Why this order:** pytest-cov has no backlog, so it's
the lowest-risk "wire the gate" first step. Ruff is
mostly mechanical (style + security) so the burn-down
is fast. Mypy is semantic (real type errors) so the
burn-down is slow and should come after we've
established the ratchet discipline on the easier tools.

## §4. What this BBF does NOT do (out of scope)

- **No code changes.** This is a doc-only BBF.
- **No config changes.** The existing `pyproject.toml`
  configs are unchanged.
- **No CI changes.** The existing `smoke.yml` is
  unchanged.
- **No `.gitignore` change.** The `tmp_*.py` footgun is
  flagged (§1, gap #1) but the fix is a separate
  housekeeping BBF (likely a 1-line `.gitignore`
  addition).
- **No tool installation.** The 3 tools may not be in
  the venv today; that's a separate concern.
- **No burn-down.** Stage 1 of the ratchet (§2) is a
  separate BBF.
- **No ratchet implementation.** Stage 2 of the ratchet
  (§2) is a separate BBF.
- **No CI wiring.** Stage 3 of the ratchet (§2) is a
  separate BBF.

## §5. Honest disclosures

1. **The "wire the gate" framing is what the ledger entry
   explicitly warns against.** This BBF is the
   ratchet-strategy brief, not the gate-wiring. The
   Stage 1+2+3 split is the only honest path to a green
   CI gate.
2. **The 131 untracked `tmp_*.py` files are a pre-condition
   problem.** Any of the 3 tools run against the repo
   root today will trip on these files first. The
   `.gitignore` fix is a separate housekeeping BBF.
3. **The 2026-08-25 backlog numbers are stale.** This
   BBF trusts them; Stage 1 (a separate BBF) should
   re-measure. The numbers may have drifted if any
   recent BBF touched the affected files (e.g., the
   FU-22-impl work added new files that ruff may now
   flag).
4. **`pytest-cov` has no existing baseline.** Whatever
   coverage the project has today is "the baseline" by
   definition. Ratcheting up from a low baseline is
   easier than starting from zero.
5. **`mypy --install-types` may surface upstream library
   issues.** The `chess.*` override is broad; the actual
   `chess` library is untyped (it's a small
   `python-chess` fork, possibly the
   upstream). Stage 1 may need to add more overrides.
6. **The `tmp_*.py` audit-layer files are operational,
   not source.** They are intentionally untracked
   (per the audit layer's design); the `.gitignore`
   fix is a clean way to keep them out of tool scans
   without changing the audit layer's behavior.
7. **The brief does not commit to a ratchet
   implementation order.** The order in §3 is a
   recommendation; the user may prefer a different
   order (e.g., ruff first because it has the most
   findings and the user wants the codebase clean).
8. **The brief does not commit to a CI workflow
   placement.** The ratchet could go in `smoke.yml`
   (existing workflow, 12 jobs already) or a new
   `quality.yml` (cleaner separation of concerns,
   but a new file). This is a Stage 3 decision.

## §6. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry
  (the original ledger entry; this BBF is the
  ratchet-strategy brief that the entry explicitly
  asked for).
- `pyproject.toml` lines 55-63 (the `[dev]` extras).
- `pyproject.toml` lines 102-116 (`[tool.ruff]`,
  `[tool.ruff.lint]`, `[tool.ruff.lint.per-file-ignores]`).
- `pyproject.toml` lines 119-129 (`[tool.mypy]` + the
  `chess.*` override).
- `pyproject.toml` lines 138-148 (`[tool.coverage.run]`
  + `[tool.coverage.report]`).
- `.github/workflows/smoke.yml` line 114 (the
  unrelated "i18n key coverage" check in the desktop
  frontend lint job).
- `.gitignore` (the missing `tmp_*.py` rule, flagged
  in §1 gap #1).
- `docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md`
  (the recent BBF that did its own byte-integrity
  checks; pattern reference for the ratchet Stage 1
  "burn-down" tracking).

## §7. Final report format

This BBF ships 1 file:

| File | Status | Lines | Purpose |
|---|---|---|---|
| `docs/16_audit/BBF-FU-29-scoping-brief.md` | NEW | this file | The ratchet-strategy brief |

**Total: 1 file, +this file's lines.**

## §8. The "AND THEN" link to the FU-29-status-check BBF

The user's directive was `go FU-29-scoping-brief AND THEN
go FU-29-status-check`. The status-check BBF is a
read-only + ledger-edit BBF that runs the current
state of the 3 tools (`ruff check . --statistics`,
`mypy services/ --json`, `pytest-cov` is harder
since coverage has never been measured) and updates
the FU-29 ledger entry with the current numbers.
The status check is the natural Stage 0 of the
ratchet (re-measure the backlog before committing
to a burn-down order).
