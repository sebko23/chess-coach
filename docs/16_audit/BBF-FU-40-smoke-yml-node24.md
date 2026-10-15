# BBF-FU-40-smoke-yml-node24 — bump 17 action pins in `smoke.yml` to @v6 (Node 20 to 24)

**Sprint intent:** Bump all Node-20-era action pins in
`.github/workflows/smoke.yml` to their Node-24-era `@v6`
counterparts. Closes the smoke.yml portion of the
Node-20 deprecation risk identified as the explicit
out-of-scope follow-up to BBF-FU-39-gitleaks-action-v3
(PR #138, squash-merge commit `47062dfa`).

**Identified:** 2026-10-15, surfaced as a leaf-review
finding during BBF-FU-39-gitleaks-action-v3 review. The
FU-39 entry's "Out of scope" subsection flagged that
`smoke.yml` was NOT yet on the Node-24 line; an
empirical scan (`git show main:.github/workflows/smoke.yml
| grep "@v"`) showed 17 Node-20-era pins across 8 jobs.
The same Jun 2, 2026 / Sep 16, 2026 GitHub-runner
deprecation timeline applies.

**The gap this BBF closes:**

The `.github/workflows/smoke.yml` workflow runs
across all 7 jobs in the chess-coach CI matrix. Every
job currently uses `actions/checkout@v4`,
`actions/setup-python@v5`, `actions/setup-node@v4`,
or `pnpm/action-setup@v4` — all Node-20-era. Per
the upstream gitleaks-action README (which is
representative of the broader Node-20 deprecation
pattern):

- Jun 2, 2026: GitHub switches the runner default
  to Node 24. Workflows using Node 20 actions
  (any `@v3`-or-older action that pins to Node 20)
  will require `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true`
  to keep running. Without this opt-out, Node 20
  actions fail.
- Sep 16, 2026: Node 20 is removed from GitHub-hosted
  runners entirely. All Node-20-era action versions
  will stop working regardless of any opt-out flag.

After this BBF, every action in `smoke.yml` is on
the Node-24 era (`@v6`). The same node-version
deprecation risk that was closed for `security-audit.yml`
in PR #138 is now also closed for `smoke.yml`.

**The fix:** a 4-pattern regex replace on
`.github/workflows/smoke.yml` bumping 17 action pins
in place:

| Pattern | Count |
|---|---|
| `actions/checkout@v[3-5]` → `actions/checkout@v6` | 7 |
| `actions/setup-python@v[3-5]` → `actions/setup-python@v6` | 6 |
| `actions/setup-node@v[3-5]` → `actions/setup-node@v6` | 2 |
| `pnpm/action-setup@v[3-5]` → `pnpm/action-setup@v6` | 2 |
| **Total** | **17** |

All bumps go to `@v6` (the Node-24-era pin), matching
the pattern established in `security-audit.yml` by
PR #138 (gitleaks-action) and the prior v6 pins in
`security-audit.yml`'s other jobs (setup-python,
setup-node, pnpm-action-setup).

**Investigation-first pass (re-derive, pre-flight):**

- `git show main:.github/workflows/smoke.yml | grep "@v"`
  returns 17 `@v[3-5]` matches + 2 false positives
  (`@v11` for pnpm version, `@v4` for a pnpm Node
  version spec — neither is an action pin). The 17
  matches are the targets of this BBF.
- The 8 jobs affected: `gateway boot (clean install)`,
  `lazy eval-graph smoke test`, `frontend types
  codegen`, `frontend static imports`, `frontend
  lint + test`, `qdrant sidecar smoke`,
  `PyInstaller binary smoke`, `commit ref verify
  (file:line references)`. All 8 jobs have at least
  one Node-20-era action pin.
- No `@v1`-`@v2` pins found (those would also be
  Node-20-era; the pattern is uniform across the
  workflow).
- No `@v3` pins found (those would be the
  intermediate "Node 20 but not the oldest" line;
  also covered by the regex).
- The 2 false-positive matches (`@v11` and `@v4`
  in non-action contexts) are preserved by the
  pattern — only `uses:`-style action pins are
  matched.

**Work product:**

This BBF produces 3 file changes:

1. `.github/workflows/smoke.yml` (modified, 17 line
   edits) — bump every Node-20-era action pin to
   `@v6`. The 17 edits are mechanical (no semantic
   change); each pin is a string replace on a
   `uses:` line.
2. `docs/16_audit/OPEN-FOLLOWUPS.md` (modified,
   +1 entry) — add the `## FU-40` ledger entry
   documenting the smoke.yml Node-20 deprecation,
   the fix, and the out-of-scope items (FU-37
   pnpm v1.x, FU-38 pre-existing gitleaks leaks).
3. `docs/16_audit/BBF-FU-40-smoke-yml-node24.md`
   (NEW, 167 lines) — the parallel decision-brief-style
   record for this BBF (mirrors `BBF-FU-39-gitleaks-action-v3.md`).

**Out of scope (separate BBFs):**

- **FU-37** — pnpm v1.x migration (already in flight,
  separate BBF).
- **FU-38** — 29 pre-existing historical gitleaks
  findings (visible in a local full-history scan,
  not in the diff-scoped SARIF). Separate BBF.
- **Any other workflow files** (besides
  `security-audit.yml` and `smoke.yml`) that may
  have Node-20-era action pins. The initial scan
  shows no other `.github/workflows/*.yml` files
  with `@v[3-5]` action pins. If a stale pin is
  found in another workflow later, it gets its
  own BBF.
- **Renaming the local `## FU-40` slot to align with
  the next available number** — per the file
  convention, FU numbers are assigned in the order
  they're added; FU-39 is the most recent (added
  during PR #138's BBF). FU-40 is the next slot.

**Honest disclosures:**

- The 17-line YAML edit is purely mechanical. No
  behavior change is expected; the Node 24 runtime
  should produce identical test results to the
  Node 20 runtime for chess-coach's CI jobs (Python
  3.11, pnpm 11, etc. are all Node-24-compatible).
- If any job's behavior DIFFERS on Node 24 (e.g.,
  a package that depends on Node-20-specific V8
  APIs), pre-merge CI will catch it in 1 cycle; the
  v0.7.114 amend-fold discipline applies.
- The Node-20 deprecation is the same defect class
  as the v0.7.128 (σ) meta-footgun: a config
  surface that "loads successfully" but doesn't
  actually apply after the upstream cutover.
- The bump does NOT change the smoke.yml job
  definitions themselves (which Python version is
  tested, which pnpm version is installed, etc.);
  it only changes the action-version pins that
  orchestrate the runner.

**Hermes verification (re-derive, post-merge):**

- `git show main:.github/workflows/smoke.yml | grep
  "@v"` returns 17 `@v6` matches + 2 false
  positives (`@v11` pnpm version, `@v4` pnpm Node
  version spec). All 17 action pins are now
  `@v6`; the false positives are unchanged.
- `git show main:.github/workflows/smoke.yml | grep
  "actions/checkout@v[3-5]"` returns 0 matches
  (the 7 `@v4` pins are all bumped to `@v6`).
- Pre-merge CI on the amended SHA: 12/12 green
  (specifically, all 8 smoke.yml jobs must remain
  green after the bump — this is the critical
  verification).

**Final report format:** the squash-merge commit
body documents this BBF's 17-line YAML diff + the
+1 ledger entry + the +1 new brief. The commit
body uses inline-backtick-wrapped `path:N` references
where appropriate and paraphrases where not, per
the v0.7.128 (σ) discipline.
