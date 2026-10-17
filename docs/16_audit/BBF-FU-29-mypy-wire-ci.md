# BBF-FU-29-mypy-wire-ci — FU-29 Stage 3 (mypy CI gate)

**Sprint intent:** Complete the FU-29 ratchet
(per `BBF-FU-29-scoping-brief.md` §2, shipped at
`e2da99c7`) by wiring the **mypy strict** check to CI
as a required check. After this BBF, both Stage 1
(ruff + mypy at 0) and Stage 3 (CI gates for both)
are COMPLETE.

**Status:** CI-config-only BBF. 1 file modified
(`.github/workflows/smoke.yml`).

## §1. The new CI job

The new `mypy` job follows the existing `ruff` job
pattern (added in `BBF-FU-29-ruff-wire-ci.md` at
`squash 98780986`):

```yaml
  mypy:
    name: mypy strict
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - name: Install chess-coach + dev deps
        # mypy needs the chess_coach package importable so it can
        # resolve cross-package imports (e.g. `from chess_coach.X
        # import Y`). `pip install -e .[dev]` installs the
        # package in editable mode and pulls mypy from
        # [project.optional-dependencies] dev = [..., "mypy>=1.10"].
        # FU-29 Stage 3: after the Stage 1 mypy burn-down
        # (BBF-FU-29-mypy-* chain, culminating in
        # BBF-FU-29-mypy-misc-followup at ed258fdc), mypy is at
        # 0 errors with strict mode enabled, so this gate can
        # fail the build on any new mypy error.
        run: |
          python -m pip install --upgrade pip --quiet
          pip install -e '.[dev]'

      - name: Run mypy strict
        # Match the [tool.mypy] config in pyproject.toml:
        # - python_version = "3.11"
        # - strict = true (warn_unused_ignores, disallow_untyped_defs, etc.)
        # - show_error_codes = true
        # - mypy_path = "libs:services:apps/cli"
        # The 4 [tool.mypy.overrides] blocks (chess.*, aiosqlite,
        # keyring, sentence_transformers, sklearn.metrics.pairwise)
        # silence missing-import errors for untyped third-party libs.
        # FU-29-ruff-burndown established ruff at 0 findings; this
        # job establishes mypy at 0 errors as a required CI gate.
        run: mypy libs services apps/cli --no-incremental
```

## §2. The verification (live, this session)

```
# Before (post-BBF-FU-29-mypy-misc-followup):
$ mypy libs services apps/cli --no-incremental
Success: no issues found in 86 source files

# This BBF adds the CI job to enforce this on every PR.
```

**Mypy is at 0 errors with strict mode.** The new
CI job will fail the build on any new mypy error.

## §3. The §1.3 catches (exemplary discipline)

1. **CRLF footgun** (pre-commit) — Python's `f.write()`
   on Windows converted the entire smoke.yml from LF
   to CRLF, which would have been a 602-line diff
   (the entire file rewritten). The amend (this
   session) converted the file back to LF to match
   HEAD. The final diff is +41 lines (the new mypy
   job + a blank line separator).

## §4. FU-29 ratchet status (post this BBF)

| Tool | Stage 1 (burn-down) | Stage 2 (baseline) | Stage 3 (wire CI) |
|---|---|---|---|
| **ruff** | **✓ DONE** (`a27da3f9`) | n/a | **✓ DONE** (`98780986`) |
| **mypy** | **✓ DONE — 0 errors** (`ed258fdc`) | TODO | **✓ DONE** (this BBF) |
| **pytest-cov** | TODO (no baseline) | TODO | TODO |

**FU-29 Stage 3 is COMPLETE for both ruff AND mypy.**
The only remaining FU-29 sub-task is pytest-cov
(no baseline exists yet).

## §5. The CI job count

Before this BBF: 13 jobs (ruff, frontend imports,
frontend types codegen, frontend lint + test,
gateway boot, gitleaks, lazy eval-graph smoke,
pip-audit, pnpm audit, qdrant sidecar, uv lock,
PyInstaller binary smoke, commit ref verify).

After this BBF: **14 jobs** (added mypy strict).

## §6. Honest disclosures

1. **The job is `mypy` (lowercase)** to match the
   `ruff` job naming convention. The display name
   is "mypy strict" to distinguish it from any future
   non-strict mypy job.

2. **The job uses `pip install -e '.[dev]'`** (not
   just `pip install mypy`) because mypy needs the
   `chess_coach` package importable to resolve
   cross-package imports. The `[dev]` extras include
   `mypy>=1.10` per `pyproject.toml` lines 55-63.

3. **The `--no-incremental` flag is used** to force
   a full type check on every CI run. This catches
   errors that incremental checking might miss
   (e.g., when a function's signature changes but
   the cache is stale).

4. **The job does NOT have `continue-on-error`** —
   it will fail the build on any mypy error. This
   is the strict-mode gate that FU-29 Stage 3
   promised.

5. **The 4 `[tool.mypy.overrides]` blocks** (chess.*,
   aiosqlite, keyring, sentence_transformers,
   sklearn.metrics.pairwise) silence missing-import
   errors for untyped third-party libraries. These
   were added in `BBF-FU-29-mypy-burndown` (squash
   `8c06036d`) and are load-bearing for the mypy
   strict gate.

6. **No new tests added.** This is a CI-config-only
   change. The existing test suite is unchanged.

7. **The 13/13 CI green on `ed258fdc` (the
   FU-29-mypy-misc-followup ship) is preserved.**
   This BBF adds 1 new job (mypy strict) to the
   existing 13; the new job will run alongside the
   others and should pass on the first try since
   mypy is at 0 errors.

## §7. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry.
- `docs/16_audit/BBF-FU-29-scoping-brief.md` (e2da99c7).
- `docs/16_audit/BBF-FU-29-status-check.md` (8e4e62e3).
- `docs/16_audit/BBF-FU-29-ruff-burndown.md` (a27da3f9).
- `docs/16_audit/BBF-FU-29-ruff-wire-ci.md` (98780986).
- `docs/16_audit/BBF-FU-29-mypy-burndown.md` (8c06036d).
- `docs/16_audit/BBF-FU-29-mypy-type-arg.md` (8de8cd27).
- `docs/16_audit/BBF-FU-29-mypy-misc.md` (2f39ac96).
- `docs/16_audit/BBF-FU-29-mypy-no-untyped-def.md` (bc944a1d).
- `docs/16_audit/BBF-FU-29-mypy-no-any-return.md` (366ceca7).
- `docs/16_audit/BBF-FU-29-mypy-misc-followup.md` (ed258fdc).
- `pyproject.toml` lines 55-63 (the `[dev]` extras).
- `pyproject.toml` lines 119-129 (the `[tool.mypy]` config).
- `pyproject.toml` lines 130-161 (the 2 `[tool.mypy.overrides]` blocks).
- `.github/workflows/smoke.yml` lines 563-602 (the new `mypy` job).
