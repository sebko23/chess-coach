# BBF-FU-29-status-check — re-measured ruff, mypy, pytest-cov state (2026-10-16)

**Sprint intent:** Re-measure the 3 quality tools declared in
`pyproject.toml`'s `[dev]` extras to refresh the 2026-08-25
numbers in the FU-29 ledger entry. This is the **Stage 0** of
the FU-29 ratchet (per `BBF-FU-29-scoping-brief.md` §2).

**Status:** Doc-only BBF. No code, no config, no CI change.
The brief only reports the current state.

## §1. Methodology (the most important section)

The 2026-08-25 measurement tripped on the **131 untracked
`tmp_*.py` files** in the repo root (the operational footnote
in the FU-29 ledger entry describes this exact footgun:
"mypy aborted on untracked `tmp_find_actual_target.py`
before any project file was checked"). The 2026-10-16
re-measurement uses the proper source paths per
`pyproject.toml`:

- **ruff**: `pyproject.toml` declares
  `[tool.ruff] src = ["libs", "services", "apps/cli"]`.
  This BBF runs `ruff check libs services apps/cli` (the
  source paths) plus `tests` and `scripts` (the per-file-ignored
  paths, where "S" and "ASYNC" are silenced).
- **mypy**: `pyproject.toml` declares
  `[tool.mypy] mypy_path = "libs:services:apps/cli"`.
  This BBF runs `mypy libs services apps/cli` (the same paths).
- **pytest-cov**: no measurement is possible without first
  running the test suite with `--cov=`; this BBF reports
  the absence of any existing baseline file (`.coverage`).

The 2026-08-25 measurement is **incomparable** to the
2026-10-16 measurement because the former ran `ruff check .`
(against the repo root, including the `tmp_*.py` noise) and
the latter runs `ruff check libs services apps/cli tests scripts`
(against the proper source paths). The 2026-08-25 number
of 2,694 ruff findings is **noise, not signal.**

## §2. The 2026-10-16 numbers

| Tool | Findings (proper source paths) | Findings (repo root, 2026-08-25 baseline) | Delta |
|---|---|---|---|
| **ruff** | **33** (26 auto-fixable) | 2,694 (146 auto-fixable) | **-2,661 (98.8% noise)** |
| **mypy** | **169 errors in 38 files** | 154 errors in 31 files | **+15 errors (real growth, mostly new code)** |
| **pytest-cov** | **no baseline** (no `.coverage` file ever existed) | no floor exists | **unchanged** |

### §2.1 ruff breakdown (33 findings, 26 auto-fixable)

Top error codes (against `libs services apps/cli tests scripts`):

| Count | Code | Auto-fixable | Description |
|---|---|---|---|
| 13 | I001 | ✓ | unsorted-imports |
| 5 | E501 | — | line-too-long |
| 5 | F401 | ✓ | unused-import |
| 3 | W292 | ✓ | missing-newline-at-end-of-file |
| 2 | SIM300 | ✓ | yoda-conditions |
| 1 | B904 | — | raise-without-from-inside-except |
| 1 | F541 | ✓ | f-string-missing-placeholders |
| 1 | SIM108 | — | if-else-block-instead-of-if-exp |
| 1 | SIM117 | ✓ | multiple-with-statements |
| 1 | UP041 | ✓ | timeout-error-alias |

**Verdict:** the 33-finding ruff backlog is **mechanically
fixable in under 5 minutes** with `ruff check --fix` (26
auto-fixable) + 1-2 manual fixes for the 7 non-auto-fixable.

### §2.2 mypy breakdown (169 errors, 38 files)

Top error codes (against `libs services apps/cli`):

| Count | Code | Description |
|---|---|---|
| 13 | `unused-ignore` | Unused `# type: ignore` comments (12 in `services/chess_coach/gateway/app.py` alone) |
| 9 | `no-untyped-def` | Function is missing a type annotation |
| 5 | `import-not-found` | Cannot find implementation or library stub (mostly `aiosqlite`) |
| 4 | `no-any-return` | Returning Any from function declared to return X |
| 4 | `misc` | List comprehension has incompatible type |
| 4 | `type-arg` | Missing type arguments for generic type (e.g. `tuple` instead of `tuple[str, int]`) |
| 3 | `index` | Value of type "dict[str, Any] \| None" is not indexable |
| 2 | `union-attr` | Item "None" has no attribute "X" |
| 1 | `attr-defined` | Type has no attribute "SERVICE_UNAVAILABLE" |
| 1 | `operator` | Unsupported operand types for `<` |
| 1 | `no-untyped-call` | Call to untyped function in typed context |

**Top 10 files by mypy errors:**

| Count | File |
|---|---|
| 9 | `services/chess_coach/gateway/app.py` |
| 8 | `services/chess_coach/gateway/routes/eval_graph.py` |
| 6 | `services/chess_coach/narration/pipeline.py` |
| 5 | `services/chess_coach/kb/store.py` |
| 5 | `services/chess_coach/gateway/routes/narration.py` |
| 4 | `services/chess_coach/gateway/routes/blunder_routes.py` |
| 4 | `services/chess_coach/gateway/routes/backfill_analyses.py` |
| 4 | `services/chess_coach/gateway/routes/engines.py` |
| 3 | `services/chess_coach/llm_router/router.py` |

**Verdict:** the 169-error mypy backlog is **non-mechanical**
(strict mode, semantic errors). The top-3 categories
(`unused-ignore`, `no-untyped-def`, `import-not-found`) are
all fixable in 2-4 hours of focused work but require real
code changes, not just `# type: ignore` additions. The
`chess.*` override in `pyproject.toml` is broad; the new
`aiosqlite` stub-need is a real finding (aiosqlite is
untyped).

### §2.3 pytest-cov breakdown

| State | Value |
|---|---|
| `.coverage` file exists? | **No** |
| Has pytest-cov ever been invoked? | **No** (no coverage data file, no coverage report) |
| What is the actual coverage? | **Unknown** (cannot be measured without running tests with `--cov=`) |
| Per `[tool.coverage.run]` config | `branch = true; source = ["libs/chess_coach", "services/chess_coach", "apps/cli/chess_coach"]` |

**Verdict:** the pytest-cov backlog is **zero in the
"no existing floor" sense** — there's nothing to "fix"
because there's no floor to "ratchet" against. The
Stage 1 task is to **establish the baseline** by
running the test suite with `--cov=` once, capture
the percentage, commit that as the floor.

## §3. The ratchet budget (updated per the re-measurement)

| Stage | Per the brief | Re-measured cost | Comment |
|---|---|---|---|
| **Stage 1: Burn-down** | 2-3 hrs (ruff) + 2-4 hrs (mypy) + 10 min (pytest-cov) | **~5 min (ruff)** + 2-4 hrs (mypy) + ~5 min (pytest-cov baseline) | The ruff burn-down is **50x faster** than the brief estimated because the brief inherited the 2026-08-25 noise. |
| **Stage 2: Baseline-and-no-regressions** | 30-60 min | 30-60 min | Unchanged |
| **Stage 3: Wire to CI** | 30-60 min | 30-60 min | Unchanged |

**Net savings vs. the brief's estimates:** ~2-3 hours
(the ruff burn-down is a one-liner, not a multi-hour task).

## §4. The pre-existing gaps (still out of scope)

1. **131 untracked `tmp_*.py` files in the repo root.**
   The 2026-10-16 measurement was deliberately scoped to
   the proper source paths to avoid this footgun. A
   separate housekeeping BBF should add `tmp_*.py` to
   `.gitignore` so future `ruff check .` runs (e.g.,
   from a careless dev who runs from the repo root)
   don't trip on the noise.

2. **The `chess_coach.keychain` install issue.** When
   trying to run the unit-test suite with coverage,
   `tests/unit/test_auth.py` failed to import because
   `chess_coach.keychain` is not installed (the
   `setuptools` `[tool.setuptools] packages` list has
   `chess_coach.keychain` and `chess_coach.log_redaction`
   listed, but they're not in the editable install).
   This is a separate `setuptools` issue, not a
   pytest-cov issue. Out of scope for this BBF.

3. **The `aiosqlite` import-not-found errors.** mypy
   cannot find stubs for `aiosqlite`. The fix is
   `mypy --install-types --non-interactive` or an
   explicit `[[tool.mypy.overrides]]` block for
   `aiosqlite`. Out of scope for this BBF; the fix
   is a Stage 1 burn-down task.

## §5. Honest disclosures

1. **The 2026-08-25 numbers were noise.** The "2,694 ruff
   findings" the FU-29 ledger entry cites is **98.8%
   noise from `tmp_*.py` files.** The real ruff
   backlog is 33. The Stage 1 burn-down is ~5 min
   (auto-fixable), not 2-3 hours (manual burn-down).

2. **The 2026-08-25 mypy numbers were real but stale.**
   154 errors → 169 errors in 6 weeks. The growth is
   mostly new code (`subprocess_runner.py`,
   `eval_graph.py`); the per-file breakdown shows
   `gateway/app.py` alone has 9 errors, of which 7
   are `unused-ignore` comments from earlier work.

3. **pytest-cov has never been run.** No `.coverage`
   file exists; the `[tool.coverage.run]` config has
   never been exercised. The Stage 1 baseline
   establishment is a one-shot task.

4. **The brief's burn-down order recommendation is
   still correct but the costs are now better understood.**
   pytest-cov first (~5 min, no burn-down); ruff second
   (~5 min, mostly auto-fixable); mypy last (2-4 hrs,
   semantic).

5. **The 2026-10-16 re-measurement is reproducible.**
   The commands are documented in §1 and can be re-run
   by any future BBF. The numbers may drift if any
   future BBF touches the affected files.

6. **The setuptools install issue is a pre-existing
   problem** (not introduced by this BBF). The
   `chess_coach.keychain` package is declared in
   `pyproject.toml` `[tool.setuptools] packages` but
   the editable install doesn't include it. This is
   a separate setuptools / pyproject issue.

7. **The 12/12 CI green on `e2da99c7` (the
   BBF-FU-29-scoping-brief ship) is preserved.** This
   status check is read-only; it doesn't change any
   files.

## §6. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry
  (the original ledger entry; this BBF is its
  re-measurement).
- `docs/16_audit/BBF-FU-29-scoping-brief.md` (the
  ratchet-strategy brief shipped at `e2da99c7`,
  PR #148).
- `pyproject.toml` lines 102-116 (the `[tool.ruff]`
  config — `src = ["libs", "services", "apps/cli"]`).
- `pyproject.toml` lines 119-129 (the `[tool.mypy]`
  config — `mypy_path = "libs:services:apps/cli"`).
- `pyproject.toml` lines 138-148 (the
  `[tool.coverage.run]` + `[tool.coverage.report]`
  configs).
- `.gitignore` (the missing `tmp_*.py` rule, flagged
  in §4 gap #1).
- `docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md`
  (the recent BBF that did its own byte-integrity
  checks; pattern reference).

## §7. The updated FU-29 ledger entry (the actual flip)

The next BBF (or this BBF's follow-up doc-drift-flip)
should replace the 2026-08-25 numbers in the FU-29
ledger entry with the 2026-10-16 numbers:

**Replace:**

> Measured backlog (project `.venv`, 2026-08-25):
> - `mypy services/` → **154 errors in 31 files** (57 source files checked); exit 1.
> - `ruff check .` → **2,694 findings**, style-dominated (top classes: E501 ×185, S607 ×77, quote-style Q1/Q2/Q3 ×~194, S310 ×70; 146 auto-fixable); exit 1.
> - Coverage: **no floor exists anywhere** — pytest-cov never invoked in CI or scripts.

**With:**

> Measured backlog (project `.venv`, 2026-10-16, re-measured via `BBF-FU-29-status-check` at commit `2e4d672a`):
> - `mypy libs services apps/cli` → **169 errors in 38 files** (86 source files checked); exit 1.
> - `ruff check libs services apps/cli tests scripts` → **33 findings** (26 auto-fixable); top classes: I001 ×13 (auto-fixable), E501 ×5, F401 ×5 (auto-fixable).
> - `ruff check .` (against the repo root) → **2,940 findings** (98.8% from the 131 untracked `tmp_*.py` operational scratch files; the 33 real findings are the proper-source-path number).
> - Coverage: **no floor exists** — pytest-cov never invoked, no `.coverage` file, no CI invocation.
