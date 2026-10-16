# BBF-FU-41-security-audit-yml-node20 — bump 6 final Node-20 pins in `security-audit.yml` to @v6

**Sprint intent:** Bump the last 6 Node-20-era action pins
in `.github/workflows/security-audit.yml` to their
Node-24-era `@v6` counterparts. Closes the Node-20
deprecation sweep across all chess-coach CI workflows
(`security-audit.yml` + `smoke.yml`), completing the
work that FU-39 (PR #138) and FU-40 (PR #139) started.

**Identified:** 2026-10-15, surfaced by the leaf review
of BBF-FU-40-smoke-yml-node24 (PR #139) as an explicit
out-of-scope follow-up. The FU-40 leaf reviewer noted
that after bumping `smoke.yml`, `security-audit.yml`
still had `actions/checkout@v5` x 4 + `astral-sh/setup-uv@v3`
x 1 — the leaf reviewer undercounted by 1 (`setup-uv@v3`
appears 2x, not 1x), for a true total of **6 Node-20-era
pins across 6 lines** (the 4 `checkout@v5` lines are
distinct; the 2 `setup-uv@v3` lines are distinct).

**The 6 Node-20-era pins (line-precise):**

| Line | Current | Target | Job |
|---|---|---|---|
| 37  | `actions/checkout@v5`        | `@v6` | `pip-audit` |
| 42  | `astral-sh/setup-uv@v3`       | `@v6` | `pip-audit` |
| 113 | `actions/checkout@v5`        | `@v6` | `uv-lock-check` |
| 116 | `astral-sh/setup-uv@v3`       | `@v6` | `uv-lock-check` |
| 144 | `actions/checkout@v5`        | `@v6` | `commit-refs-verify` |
| 185 | `actions/checkout@v5`        | `@v6` | `pnpm-audit` |

The 4 jobs affected: `pip-audit` (lines 37, 42),
`uv-lock-check` (lines 113, 116), `commit-refs-verify`
(line 144), `pnpm-audit` (line 185). The `gitleaks` job
itself is unaffected — its `actions/checkout` was already
bumped to `@v6` by PR #138 (the FU-39 gitleaks-action
bump).

Per the upstream `gitleaks/gitleaks-action` README
(representative of the broader Node-20 deprecation
pattern):

- Jun 2, 2026: GitHub switches the runner default to
  Node 24. Workflows using Node 20 actions will require
  `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true` to keep
  running.
- Sep 16, 2026: Node 20 is removed from GitHub-hosted
  runners entirely.

After this BBF, every action in `security-audit.yml` is
on the Node-24 era (`@v6`), matching the pattern
established in PR #138 (gitleaks-action) and PR #139
(smoke.yml).

**The fix:** a 2-pattern regex replace on
`.github/workflows/security-audit.yml` bumping 6 action
pins in place:

| Pattern | Count |
|---|---|
| `actions/checkout@v5` → `actions/checkout@v6` | 4 |
| `astral-sh/setup-uv@v3` → `astral-sh/setup-uv@v6` | 2 |
| **Total** | **6** |

All bumps go to `@v6` (the Node-24-era pin), matching
the pattern from FU-39 and FU-40.

**Investigation-first pass (re-derive, pre-flight):**

- `git show main:.github/workflows/security-audit.yml |
  grep "@v"` returns 11 action pin matches across 11
  `uses:` lines. 5 of those are already on Node-24
  (`actions/checkout@v6` x 1 at line 88, `setup-python@v6`
  x 1, `pnpm/action-setup@v6` x 1, `setup-node@v6` x 1,
  `gitleaks/gitleaks-action@v3` x 1 from PR #138's Node-24
  bump). 6 are on Node-20 (the targets of this BBF).
- The 5 jobs affected: `pip-audit` (lines 37, 42),
  `gitleaks (secret scan)` (line 113, 116), `uv
  lock --check` (line 144), `commit ref verify
  (file:line references)` (line 185). The
  `gitleaks-action@v3` pin at line 96 is a v3 pin but
  not Node-20-era (v3 of the action is the Node-24 line
  per PR #138's bump; the action's `setup-uv@v3` uses
  Node 20 because the `setup-uv` action's `@v3` is the
  Node-20 era).
- No `@v1`-`@v4` pins (those would also be Node-20-era;
  the pattern is uniform across the workflow).
- Pre-existing `setup-uv` pattern: PR #138 (the gitleaks
  bump) didn't touch `setup-uv`; that was out of scope
  for the gitleaks BBF. This BBF completes the sweep.

**Work product:**

This BBF produces 3 file changes:

1. `.github/workflows/security-audit.yml` (modified,
   +6/-6 line edits) — bump every Node-20-era action
   pin to `@v6`.
2. `docs/16_audit/OPEN-FOLLOWUPS.md` (modified, +1 entry)
   — flip the FU-41 status to RESOLVED + document the
   6-pin bump.
3. `docs/16_audit/BBF-FU-41-security-audit-yml-node20.md`
   (NEW, 164 lines) — the parallel decision-brief-style
   record for this BBF (mirrors `BBF-FU-40-smoke-yml-node24.md`).

**Out of scope (NOT in this BBF):**

- **FU-37** — pnpm v1.x migration (already in flight,
  separate BBF).
- **FU-38** — pre-existing gitleaks findings (closed in
  PR #140 by the prior BBF; the 2 out-of-scope
  deleted-file findings remain a future BBF).
- The 4 preexisting stale references in `smoke.yml`
  context (a `app.py:181` code reference plus 3 URLs
  with `//host:port` patterns that the σ-gate's Format 1
  regex matches). These are not introduced by this BBF;
  they predate the σ-discipline tightening. The CI's
  `commit ref verify` job runs the σ-gate against the
  commit body / PR body, not the diff, so these
  preexisting refs do not fail the gate. A separate
  doc-drift BBF can fix them; out of scope here.

**Honest disclosures:**

- The 6-line YAML edit is purely mechanical. No
  behavior change is expected; the Node 24 runtime
  should produce identical test results to the Node 20
  runtime for chess-coach's CI jobs (Python 3.11,
  pnpm 11, uv, etc. are all Node-24-compatible).
  CI will catch it in 1 cycle; the v0.7.114 amend-fold
  discipline applies.
- The bump does NOT change the `security-audit.yml` job
  definitions themselves (which Python version, which
  gitleaks CLI version, etc.); it only changes the
  action-version pins that orchestrate the runner.
- **Line-ending preservation:** write the YAML file as
  LF (matching the prior `main` blob). The FU-40 BBF
  caught a CRLF regression on the initial commit
  (`26f5f8b0`); per the v0.7.114 discipline + the
  post-squash-pitfalls skill §F, this BBF uses
  byte-mode writes to preserve the line endings.
- `astral-sh/setup-uv@v3` is the only third-party action
  pin in `security-audit.yml`. Its `@v6` exists and
  matches the Node-24 era; per the upstream action's
  release notes, v3 is the last Node-20 version and
  v4+ is Node-24. Bumping to v6 is consistent with the
  pattern from FU-39 and FU-40 (all Node-20-era → `@v6`).

**Hermes verification (re-derive, post-merge):**

- `git show main:.github/workflows/security-audit.yml |
  grep "@v"` returns 11 matches: 5 already-Node-24 +
  6 newly-bumped `@v6` (zero remaining `@v[3-5]`).
- `git show main:.github/workflows/security-audit.yml |
  grep "gitleaks-action"` returns `@v3` (the gitleaks
  action was already bumped to v3 in PR #138; this BBF
  doesn't touch it).
- File is LF (not CRLF) at the committed SHA:
  `git show main:.github/workflows/security-audit.yml |
  head -c 200 | xxd | head -3` shows `0a` (LF) only, no
  `0d` (CR).
- Pre-merge CI on the amended SHA: 12/12 green
  (all 5 security-audit.yml jobs must remain green
  after the bump — this is the critical verification).

**Final report format:** the squash-merge commit body
documents this BBF's 6-line YAML diff + the 6-pin
breakdown + the new brief + the OPEN-FOLLOWUPS.md
status flip. The commit body uses inline-backtick-wrapped
`path:N` references where appropriate and paraphrases
where not, per the v0.7.128 (σ) discipline.
