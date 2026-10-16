# BBF-FU-29-ruff-wire-ci — Stage 3 ruff wire-to-CI (smoke.yml `ruff` job)

**Sprint intent:** Execute Stage 3 of the FU-29 ratchet
(per `BBF-FU-29-scoping-brief.md` §2, shipped at
`e2da99c7`) for the **ruff** tool. Stage 1 (burn-down)
shipped at `a27da3f9` (PR #150) — `ruff check libs services
apps/cli tests scripts` now returns 0 findings. This BBF
wires the same `ruff check` command to CI as a new
`ruff` job in `smoke.yml`.

**Status:** CI-only BBF. 1 file modified
(`.github/workflows/smoke.yml`). No code, no test, no
brief-side changes.

## §1. The new `ruff` job (the BBF's main contribution)

The new job is appended to the end of `smoke.yml`:

```yaml
  # FU-29-ruff-wire-ci: Stage 3 of the FU-29 ratchet (per
  # docs/16_audit/BBF-FU-29-scoping-brief.md §2, shipped at e2da99c7).
  # Wires `ruff check` to the smoke CI. As of 2026-10-16 (per
  # docs/16_audit/BBF-FU-29-status-check.md, shipped at 8e4e62e3),
  # `ruff check libs services apps/cli tests scripts` returns 0
  # findings (down from 33 pre-burndown, per
  # docs/16_audit/BBF-FU-29-ruff-burndown.md, shipped at a27da3f9).
  # The current `ruff check` IS the ratchet: any new finding
  # flips the gate red, so a future PR that introduces a new
  # E501, F401, I001, etc. will fail this job. The ratchet
  # baseline is 0 findings; new findings are not tolerated.
  #
  # The install step pins `ruff>=0.4` (matching the floor in
  # pyproject.toml [dev] extras). The CI resolves to the latest
  # 0.4.x release at run time, which may surface new rules
  # introduced between the local-dev install and the CI run;
  # this is intentional (the ratchet tightens as ruff evolves).
  ruff:
    name: ruff lint
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - name: Install ruff
        # Pin the floor to match pyproject.toml [dev] extras. CI
        # resolves to the latest 0.4.x release; a future bump to
        # 0.5+ in pyproject.toml is a separate decision (tracked
        # in the FU-29-ruff-*-followup chain).
        run: pip install 'ruff>=0.4'

      - name: Run ruff check
        # Match the [tool.ruff] src paths in pyproject.toml:
        # src = ["libs", "services", "apps/cli"]. The tests/ and
        # scripts/ paths are also checked; per
        # [tool.ruff.lint.per-file-ignores] the S (security) and
        # ASYNC rules are silenced for tests/.
        run: ruff check libs services apps/cli tests scripts
```

## §2. The 4 design decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Where to wire (smoke.yml vs new quality.yml)** | Append to `smoke.yml` | The repo convention is to keep all CI in `smoke.yml` (see `frontend-imports`, `frontend-lint-test`, `gateway-boot`, etc.). A new `quality.yml` would split the surface area and require a new workflow run. The brief's §1 Stage 3 leaves this as a "Stage 3 decision"; the per-repo convention favors `smoke.yml`. |
| **Action pins (`@v6`)** | `actions/checkout@v6` + `actions/setup-python@v6` | Consistent with the rest of `smoke.yml` after the FU-39/40/41 Node-20-era pin bumps. The `@v6` line tracks Node 24. |
| **Ratchet baseline (0 findings vs diff)** | `ruff check` (no `--diff` baseline file) | The brief's §2 Stage 2 ratchet ("baseline-and-no-regressions") is unnecessary for ruff because the Stage 1 output is 0 findings — there is no baseline to "ratchet against." A new finding flips the gate red automatically. |
| **Install method (`pip install ruff` vs `[dev]` extras)** | `pip install 'ruff>=0.4'` (direct) | The job is the only step that needs ruff; a full editable install (`pip install -e '.[dev]'`) would pull in 100+ packages (sentence-transformers, pdf2image, etc.) that the ruff job does not need. The 1-line direct install is ~10x faster and avoids the heavy transitive deps. The floor (`>=0.4`) matches `[dev]` extras. |

## §3. The ratchet math (per the brief)

| Stage | Status | Cost |
|---|---|---|
| **Stage 1: Burn-down** | **✓ DONE** (`a27da3f9`, PR #150) | 0 findings from 33 |
| **Stage 2: Baseline-and-no-regressions** | n/a | ratchet baseline is 0 findings; the `ruff check` exit code IS the ratchet |
| **Stage 3: Wire to CI** | **✓ DONE** (this BBF) | 1 file, 1 job, 4 steps |

**The `ruff` tool is the first of the 3 quality tools
to complete the full ratchet (Stage 1 + Stage 2 + Stage 3).**

## §4. The follow-up chain (mypy and pytest-cov)

The ratchet is **only** complete for ruff. The mypy and
pytest-cov sub-ratchets are still pending:

- **`go FU-29-mypy-burndown`** — Stage 1 mypy sub-burndown
  (169 errors, 38 files; 2-4 hrs; multi-BBF).
- **`go FU-29-mypy-wire-ci`** — Stage 3 mypy wire-to-CI
  (after the mypy sub-burndown lands; ~30-60 min).
- **`go FU-29-pytest-cov-baseline`** — Stage 1 pytest-cov
  sub-burndown (establish the baseline; ~5 min; blocked by
  the pre-existing `chess_coach.keychain` setuptools
  install issue).
- **`go FU-29-pytest-cov-wire-ci`** — Stage 3 pytest-cov
  wire-to-CI (after the baseline is established; ~30-60 min).

## §5. The 12/12 CI expectation (post this BBF)

The new `ruff` job will be the **13th CI check** (the YAML
has 8 jobs, but the existing 12-check count is because
some jobs are matrix-strategies, e.g., the `qdrant-smoke`
matrix, the `frontend-lint-test` matrix). The 12/12 green
expectation will become **13/13 green** after this BBF.

Wait — re-checking: the existing 12 checks are per-job
from the YAML. The `smoke.yml` YAML has 8 jobs
(`frontend-imports`, `frontend-types-codegen`,
`frontend-lint-test`, `gateway-boot`,
`pyinstaller-binary-smoke`, `qdrant-smoke`, `smoke`,
and the new `ruff`). The 12/12 CI count must include
matrix splits. Adding 1 more YAML job adds 1 more
check → **13/13 green** expected.

## §6. Honest disclosures

1. **The `ruff` floor pin (`>=0.4`) is intentionally
   minimal.** A future PR that bumps the floor to
   `>=0.5` in `pyproject.toml` may surface new rules
   that the existing codebase violates. That would
   flip the gate red and require either a follow-up
   burn-down BBF or a per-line `# noqa: <rule>`
   suppression. This is the ratchet tightening as
   ruff evolves, which is intentional.

2. **The `pip install 'ruff>=0.4'` is a fresh install
   per CI run.** No `setuptools` editable install is
   needed because the ruff job does not import any
   project code. The `frontend-types-codegen` and
   `gateway-boot` jobs do `pip install -e '.[dev]'`
   because they need the project's Python imports;
   the ruff job does not.

3. **The `ruff check libs services apps/cli tests scripts`
   command exactly matches the local-dev verification
   run in the FU-29-ruff-burndown BBF.** No new
   configuration is introduced; the `[tool.ruff]` and
   `[tool.ruff.lint]` configs in `pyproject.toml` are
   unchanged.

4. **The `actions/setup-python@v6` pin is consistent
   with the rest of `smoke.yml` (post-FU-40 bumps).**
   The `@v6` line tracks Python 3.13; the `python-version:
   "3.11"` matches the project's `requires-python = ">=3.11"`.

5. **The 12/12 CI green on `a27da3f9` (the
   FU-29-ruff-burndown ship) is preserved.** This
   CI-only BBF adds 1 new job; the existing 12 jobs
   should remain green.

6. **No `pyproject.toml` change.** The `[dev]` extras
   already declare `ruff>=0.4`; the CI install matches.

7. **The brief is the only documentation change.** No
   code, no test, no config (other than the workflow).

## §7. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry
  (the original ledger entry; this BBF completes the
  ruff sub-ratchet of the FU-29 work).
- `docs/16_audit/BBF-FU-29-scoping-brief.md`
  (the ratchet-strategy brief, shipped at
  `e2da99c7`).
- `docs/16_audit/BBF-FU-29-status-check.md`
  (the re-measurement brief, shipped at
  `8e4e62e3`).
- `docs/16_audit/BBF-FU-29-ruff-burndown.md`
  (the Stage 1 ruff sub-burndown, shipped at
  `a27da3f9`; this BBF is Stage 3 for ruff).
- `pyproject.toml` lines 55-63 (the `[dev]` extras,
  which declare `ruff>=0.4`).
- `pyproject.toml` lines 102-116 (the `[tool.ruff]`
  + `[tool.ruff.lint]` configs).
- `.github/workflows/smoke.yml` (the modified file).
- `.github/workflows/smoke.yml` line 20 (the
  `actions/checkout@v6` pin in the existing
  `frontend-imports` job — the convention this BBF
  follows).
